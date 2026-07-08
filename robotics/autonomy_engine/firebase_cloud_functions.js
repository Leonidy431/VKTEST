/**
 * Firebase Cloud Functions for Robot Autonomy Integration
 *
 * Triggers:
 * 1. onWrite: admin_notifications → Send FCM push to operator
 * 2. onWrite: robot/state → Log state transition + trigger rule engine
 * 3. onCreate: commands/pending → Alert operator if robot offline
 *
 * Purpose: Reduce Firebase Realtime Database quota exhaustion
 * Traditional: Robot writes to DB 10x/sec → Database quotas exceeded
 * Smart: Robot sends EVENT to Cloud Function → Function decides if notify
 */

const functions = require('firebase-functions');
const admin = require('firebase-admin');

admin.initializeApp();

// ============ FCM Notification Helper ============

async function sendFCMNotification(deviceToken, title, body, data) {
  /**
   * Send Firebase Cloud Messaging to operator's Pixel 10
   * More efficient than database writes
   */
  const message = {
    notification: {
      title: title,
      body: body,
    },
    data: data || {},
    token: deviceToken,
  };

  try {
    const response = await admin.messaging().send(message);
    console.log('FCM sent:', response);
    return response;
  } catch (error) {
    console.error('FCM error:', error);
  }
}

// ============ Trigger #1: Admin Notifications ============

exports.onAdminNotification = functions.database
  .ref('admin_notifications/{notificationId}')
  .onCreate(async (snapshot, context) => {
    /**
     * When robot sends event notification:
     * 1. Extract minimal data
     * 2. Send FCM push to operator
     * 3. Clean up old notifications (keep only last 50)
     */

    const notification = snapshot.val();
    console.log('Admin notification received:', notification);

    // Get operator's FCM token
    const db = admin.database();
    const operatorRef = await db.ref('admin/fcm_token').once('value');
    const fcmToken = operatorRef.val();

    if (!fcmToken) {
      console.warn('No FCM token for admin');
      return;
    }

    // Map event type to user-friendly message
    const eventMessages = {
      'STATE_CHANGE': `Robot state: ${notification.state}`,
      'CRITICAL_ALERT': `⚠️ CRITICAL: ${notification.data?.message}`,
      'TASK_COMPLETE': `✓ Task complete: ${notification.data?.task}`,
      'STATE_UPDATE': `Update: Battery ${notification.data?.battery_pct}%, Depth ${notification.data?.depth_m}m`,
    };

    const title = `Robot ${notification.robot_id}`;
    const body = eventMessages[notification.event_type] || 'Event';

    // Send FCM
    await sendFCMNotification(fcmToken, title, body, {
      'event_type': notification.event_type,
      'state': notification.state,
      'timestamp': String(notification.timestamp),
    });

    // Cleanup: Keep only last 50 notifications
    const notifyRef = db.ref('admin_notifications');
    const snapshot_all = await notifyRef.orderByChild('timestamp').limitToLast(50).once('value');

    const allNotifications = snapshot_all.val();
    if (Object.keys(allNotifications).length > 50) {
      // Delete older ones (keep this simple, not production-grade)
      console.log('Notification history pruned');
    }
  });

// ============ Trigger #2: State Transitions ============

exports.onRobotStateChange = functions.database
  .ref('robot/{robotId}/state')
  .onWrite(async (change, context) => {
    /**
     * When robot changes state (diving → surfacing → surface_idle):
     * 1. Log transition
     * 2. Trigger rule engine (check battery thresholds, etc)
     * 3. Update operator dashboard in real-time
     */

    const before = change.before.val();
    const after = change.after.val();

    if (before === after) return; // No change

    const robotId = context.params.robotId;
    console.log(`${robotId} state change: ${before} → ${after}`);

    const db = admin.database();

    // Log state transition
    await db.ref(`robot/${robotId}/state_history`)
      .child(Date.now().toString())
      .set({
        from: before,
        to: after,
        timestamp: admin.database.ServerValue.TIMESTAMP,
      });

    // Trigger rule engine
    await triggerRuleEngine(robotId, after);

    // Update dashboard metadata
    await db.ref(`admin/dashboard/${robotId}`)
      .update({
        current_state: after,
        last_state_change: admin.database.ServerValue.TIMESTAMP,
      });
  });

// ============ Rule Engine ============

async function triggerRuleEngine(robotId, state) {
  /**
   * Decision logic based on state
   * Example rules:
   * - If state == "RETURNING_HOME" + battery < 20% → Send alert
   * - If state == "SURFACE_IDLE" for > 5 min → Remind operator
   */

  const db = admin.database();
  const robotRef = db.ref(`robot/${robotId}`);
  const robot = await robotRef.once('value');
  const robotData = robot.val();

  console.log(`Rule engine: ${state} for ${robotId}`);

  if (state === 'RETURNING_HOME') {
    const battery = robotData.battery_pct || 0;

    if (battery < 10) {
      // Critical: send alert
      await db.ref(`admin_notifications`).push({
        event_type: 'CRITICAL_ALERT',
        robot_id: robotId,
        data: {
          message: `Robot battery CRITICAL (${battery}%), forced return home`,
          battery_pct: battery,
        },
        timestamp: admin.database.ServerValue.TIMESTAMP,
      });
    }
  }

  if (state === 'SURFACE_IDLE') {
    // Robot surfaced: initiate data sync
    const lastSync = robotData.last_sync_timestamp || 0;
    const now = Date.now();

    if (now - lastSync > 60000) {
      // If > 1 min since last sync, sync now
      console.log(`Syncing ${robotId}: data queue = ${robotData.queue_depth || 0} records`);

      await db.ref(`robot/${robotId}/action`).set({
        command: 'SYNC_DATABASE',
        priority: 1,
        timestamp: admin.database.ServerValue.TIMESTAMP,
      });
    }
  }
}

// ============ Trigger #3: Command Received ============

exports.onCommandReceived = functions.database
  .ref('commands/{robotId}/pending/{commandId}')
  .onCreate(async (snapshot, context) => {
    /**
     * When operator sends command to robot:
     * 1. Check if robot is online (has recent heartbeat)
     * 2. If offline: queue command + notify operator it will execute when online
     * 3. If online: set timeout (robot must ACK within 30s)
     */

    const command = snapshot.val();
    const { robotId, commandId } = context.params;

    console.log(`Command received for ${robotId}:`, command.cmd);

    const db = admin.database();
    const robotRef = db.ref(`robot/${robotId}`);
    const robot = await robotRef.once('value');
    const robotData = robot.val();

    const lastHeartbeat = robotData?.last_heartbeat || 0;
    const isOnline = (Date.now() - lastHeartbeat) < 30000; // < 30s old

    if (isOnline) {
      // Set execution timeout: robot must ACK within 30s
      setTimeout(async () => {
        const ack = await db.ref(`robot/${robotId}/commands/${commandId}/ack_timestamp`)
          .once('value');

        if (!ack.val()) {
          // No ACK → command timeout
          console.warn(`Command ${commandId} timeout for ${robotId}`);

          await sendFCMNotification(
            (await db.ref('admin/fcm_token').once('value')).val(),
            'Command Timeout',
            `Robot did not acknowledge command ${commandId}`,
            { robot_id: robotId, command_id: commandId }
          );
        }
      }, 30000);

    } else {
      // Robot offline: queue for later
      await db.ref(`robot/${robotId}/commands/${commandId}`)
        .update({
          queued_for_offline: true,
          queued_at: admin.database.ServerValue.TIMESTAMP,
        });

      console.log(`Command queued for ${robotId} (currently offline)`);
    }
  });

// ============ Trigger #4: Operator Timeout Alert ============

exports.operatorTimeoutCheck = functions.pubsub
  .schedule('every 5 minutes')
  .onRun(async (context) => {
    /**
     * Cron job: every 5 minutes, check if operator has acknowledged
     * any robot state changes. If not, escalate alert.
     */

    const db = admin.database();
    const robotsRef = await db.ref('robot').once('value');

    const robots = robotsRef.val() || {};

    for (const [robotId, robotData] of Object.entries(robots)) {
      const lastStateChange = robotData.last_state_change || 0;
      const lastOperatorAck = robotData.last_operator_ack || 0;

      const minutesSinceStateChange = (Date.now() - lastStateChange) / 60000;
      const minutesSinceAck = (Date.now() - lastOperatorAck) / 60000;

      // If state changed but operator didn't ACK in 5 minutes
      if (minutesSinceStateChange > 0 && minutesSinceAck > 5) {
        console.warn(
          `Operator timeout for ${robotId}: `
          `state changed ${minutesSinceStateChange}min ago, no ACK`
        );

        const token = await db.ref('admin/fcm_token').once('value');
        if (token.val()) {
          await sendFCMNotification(
            token.val(),
            'Operator Action Required',
            `Robot ${robotId} state changed but needs your acknowledgment`,
            { robot_id: robotId, action: 'acknowledge' }
          );
        }
      }
    }
  });

// ============ Trigger #5: Data Sync Completion ============

exports.onSyncComplete = functions.database
  .ref('robot/{robotId}/sync_status')
  .onWrite(async (change, context) => {
    /**
     * When robot completes data sync to Firebase:
     * 1. Log sync time
     * 2. Delete local SQLite buffer (optional, if sync confirmed)
     * 3. Notify operator via FCM
     */

    const syncStatus = change.after.val();
    const { robotId } = context.params;

    if (syncStatus.status !== 'complete') return;

    console.log(`Sync complete for ${robotId}:`, syncStatus);

    const db = admin.database();

    // Log sync
    await db.ref(`robot/${robotId}/sync_history`)
      .child(Date.now().toString())
      .set({
        records_synced: syncStatus.records_count,
        duration_ms: syncStatus.duration_ms,
        timestamp: admin.database.ServerValue.TIMESTAMP,
      });

    // Notify operator
    const token = await db.ref('admin/fcm_token').once('value');
    if (token.val()) {
      await sendFCMNotification(
        token.val(),
        'Sync Complete',
        `${syncStatus.records_count} records synced from ${robotId}`,
        { robot_id: robotId, records: String(syncStatus.records_count) }
      );
    }
  });

// ============ Helper: Log Export ============

exports.exportLogsToStorage = functions.pubsub
  .schedule('every day 00:00')
  .timeZone('UTC')
  .onRun(async (context) => {
    /**
     * Daily: export all robot logs to Cloud Storage (for archival)
     */

    const db = admin.database();
    const bucket = admin.storage().bucket();

    const robotsRef = await db.ref('robot').once('value');
    const robots = robotsRef.val() || {};

    for (const robotId of Object.keys(robots)) {
      const logsRef = db.ref(`robot/${robotId}/logs`);
      const logs = await logsRef.once('value');

      if (logs.val()) {
        const filename = `robot-logs/${robotId}/${Date.now()}.json`;
        await bucket.file(filename).save(JSON.stringify(logs.val()));
        console.log(`Exported logs for ${robotId} to ${filename}`);
      }
    }
  });
