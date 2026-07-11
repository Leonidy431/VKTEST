# Technical Specification: GrapheneOS Pixel 10 Pro XL + VKTEST Cloud Integration

**Document Type:** Technical Requirement Specification (TZ)  
**Status:** Draft  
**Date:** 2026-07-11  
**Component:** Operator Interface (Layer 4 / UI Dashboard)  

---

## Executive Summary

**Goal:** Enable Pixel 10 Pro XL (running GrapheneOS) to seamlessly integrate with VKTEST autonomous AUV system via secure, privacy-preserving cloud protocol.

**Key Requirement:** No default Google Services (GrapheneOS design). Must implement custom protocol bridge.

**Protocol Stack:**
```
Layer 7 (App):     VKTEST Operator UI (Kotlin/Jetpack Compose)
Layer 6 (TLS):     mTLS + certificate pinning
Layer 5 (Crypto):  Ed25519 + AES-256-GCM
Layer 4 (Network): WebSocket over TLS (WSS) + fallback MQTT QoS 2
Layer 3 (IP):      IPv4/IPv6 dual-stack
Layer 2 (Link):    WiFi 6E (802.11ax) + 5G mmWave band-switching
```

---

## Hardware Specification

### Device: Pixel 10 Pro XL

**Specs:**
- **CPU:** Google Tensor G5 (8-core ARM)
- **RAM:** 12 GB LPDDR5X
- **Storage:** 256 GB UFS 4.0 (with encryption)
- **Display:** 6.8" QHD+ OLED (120 Hz, HDR)
- **mmWave:** Qualcomm X80 5G modem (sub-6 + mmWave bands)
- **Sensors:** 9-axis IMU, barometer, proximity, ambient light
- **Camera Array:** 
  - Main: 50 MP f/1.7 (OIS)
  - Ultrawide: 42 MP f/2.2
  - Telephoto: 12 MP f/3.5 (5× zoom)
  - Front: 20 MP f/2.2
- **Battery:** 5,600 mAh (fast charge: 0→80% in 30 min)
- **Connectivity:**
  - WiFi 7 (802.11be) — future upgrade
  - 5G NR (FR1 + FR2 mmWave)
  - NFC + UWB (Ultra Wideband)
  - Bluetooth 5.4
  - Dual SIM (nano + eSIM)

### OS: GrapheneOS

**Why GrapheneOS?**
- **Privacy:** No Google Play Services forced
- **Security:** Hardened kernel + exploit mitigations
- **Trust:** Open-source, auditable
- **Control:** User permission model (per-app sandboxing)

**Version:** GrapheneOS 2026-07 (or latest)

**Key Restrictions (to Work Around):**
- No automatic background services
- Restricted hardware access (sensors require explicit grant)
- SELinux: `enforcing` (cannot disable)
- No root access to system partition
- Storage scoped to app directory (SCOPED_STORAGE)

---

## Protocol Architecture

### 1. Device Provisioning (Zero-Touch)

**Flow:**

```
┌─────────────────────────────────────────────────────────┐
│ User scans QR code (NFC alternative available)         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ QR contains:                                            │
│  - provisioning_url: "https://vktest-cloud/provision" │
│  - device_token: one-time use JWT                      │
│  - public_key: Ed25519 (device identity)               │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ App opens URL → Cloud verifies token + device_key      │
│ Cloud generates:                                        │
│  - client_certificate.pem (1-year lifetime)            │
│  - certificate_chain.pem                               │
│  - cloud_public_key.pem (for verification)             │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│ App stores certs in KeyStore (encrypted on disk)       │
│ Transition to normal operation (mTLS mode)             │
└─────────────────────────────────────────────────────────┘
```

**Implementation (Kotlin):**

```kotlin
// 1. Parse QR code
val qrData = parseQRCode(bitmap)
val provisioningUrl = qrData.provisioning_url
val deviceToken = qrData.device_token

// 2. HTTP POST to provisioning endpoint
val provisioner = ProvisioningClient(provisioningUrl)
val response = provisioner.requestCertificate(
    device_token = deviceToken,
    public_key = deviceKeyPair.public
)

// 3. Store certificates in Android Keystore
val keyStore = KeyStore.getInstance("AndroidKeyStore")
keyStore.load(null)
val entry = KeyStore.PrivateKeyEntry(
    privateKey = deviceKeyPair.private,
    certificateChain = response.certificate_chain.toTypedArray()
)
keyStore.setEntry("vktest_client_cert", entry, params)

// 4. Prepare mTLS socket
val sslContext = SSLContext.getInstance("TLSv1.3")
val kmf = KeyManagerFactory.getInstance("X509")
kmf.init(keyStore, null)
sslContext.init(kmf.keyManagers, null, SecureRandom())
```

---

### 2. Secure Communication Protocol (mTLS + WSS)

**Connection:**

```
GrapheneOS Pixel 10 Pro XL
        ↓
    TLS 1.3 (mTLS)
    ├─ Client cert: Ed25519 signed by cloud CA
    ├─ Server cert: pinned in app (certificate pinning)
    ├─ Cipher: TLS_AES_256_GCM_SHA384
    └─ OCSP stapling: enabled
        ↓
    WebSocket over TLS (WSS)
    ├─ Path: /ws/robot/{robot_id}/operator/{operator_id}
    ├─ Subprotocol: vktest-telemetry-v1
    └─ Compression: permessage-deflate
        ↓
    VKTEST Cloud (Firebase + custom backend)
```

**Message Framing (Binary Protocol):**

```
Frame Structure (Protobuf):

Message {
  sequence_id: uint32        // Detect out-of-order delivery
  timestamp_unix_ms: uint64  // Client-server clock sync
  command_type: enum         // TELEMETRY, COMMAND_ACK, STATE_UPDATE, etc.
  payload: bytes             // Protobuf encoded sub-message
  signature: bytes           // Ed25519 signature over {sequence_id...payload}
  compression: enum          // NONE, DEFLATE, BROTLI
}
```

**Payload Types:**

```
1. TELEMETRY (Robot → Operator)
   ├─ depth_m: float
   ├─ battery_pct: int
   ├─ temperature_c: float
   ├─ position: {lat, lon, accuracy}
   ├─ camera_frame: VideoFrame (H.264 keyframe every 2 sec)
   ├─ sonar_data: SonarBurst (compressed)
   └─ status: RobotStatus enum

2. COMMAND (Operator → Robot)
   ├─ command_id: uint32 (for ACK matching)
   ├─ mission: {depth_target, heading, duration}
   ├─ control: {thrust_vector, rotation_rate}
   ├─ data_priority: Priority enum
   └─ ttl_sec: time-to-live (auto-abort if not executed)

3. STATE_UPDATE (Bidirectional)
   ├─ operational_phase: enum (PREFLIGHT, DIVING, SURFACING, etc.)
   ├─ autonomy_mode: enum (MANUAL, AUTONOMOUS, FAILSAFE)
   ├─ watchdog_heartbeat: present
   └─ error_flags: int

4. VIDEO_STREAM (Robot → Operator, optional high-bandwidth)
   ├─ frame_id: uint32
   ├─ timestamp_ms: uint64
   ├─ codec: H.264 / H.265 / VP9
   ├─ resolution: {width, height}
   └─ payload: encoded frame
```

---

### 3. GrapheneOS Permissions (Minimal, Privacy-First)

**Required Permissions (AndroidManifest.xml):**

```xml
<!-- Networking (implicit with <uses-permission>) -->
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />

<!-- 5G/mmWave detection (optional, for band-switching) -->
<uses-permission android:name="android.permission.READ_PHONE_STATE" />

<!-- Camera (if enabling live operator view of ROV) -->
<uses-permission android:name="android.permission.CAMERA" />

<!-- Location (only with user explicit grant, for homing feature) -->
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />

<!-- Storage (app-private only, scoped) -->
<uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE" />
```

**Runtime Permission Flow (Kotlin):**

```kotlin
// Only request when needed, not at app launch
if (ContextCompat.checkSelfPermission(
    context,
    Manifest.permission.CAMERA
) != PackageManager.PERMISSION_GRANTED) {
    
    ActivityCompat.requestPermissions(
        activity,
        arrayOf(Manifest.permission.CAMERA),
        REQUEST_CAMERA_PERMISSION
    )
}
```

**GrapheneOS Privacy Controls:**
- Fake GPS mode (can be toggled in settings)
- Sensors restricted (can grant per-app)
- Camera indicator light (always on when camera active)
- Microphone indicator light

---

### 4. Network Interface: WiFi 6E + 5G mmWave Band Switching

**Scenario: Operator at dock controlling deep-water AUV**

```
┌─────────────────────────────────────────┐
│ WiFi 6E (802.11ax)                      │
│ - 2.4 GHz (legacy support)              │
│ - 5 GHz (primary, low latency)          │
│ - 6 GHz (new spectrum, less congestion) │
│ - Throughput: 1–2 Gbps                  │
│ - Latency: 5–20 ms                      │
└─────────────────────────────────────────┘
              ↓ (decision logic)
        Network Quality Score:
        signal_strength + latency + loss
                  ↓
      Score < threshold? → Switch to 5G
                  ↓
┌─────────────────────────────────────────┐
│ 5G mmWave (FR2: 26–39 GHz)              │
│ - Ultra-low latency (1–5 ms)            │
│ - Peak throughput: 3–5 Gbps             │
│ - Range: 100–200 meters (line-of-sight) │
│ - Power: Higher drain (~800 mW)         │
└─────────────────────────────────────────┘
```

**Implementation (Kotlin, using NetworkInfo):**

```kotlin
fun detectBestNetwork(): String {
    val connectivityMgr = context.getSystemService<ConnectivityManager>()!!
    val activeNetwork = connectivityMgr.activeNetwork
    val caps = connectivityMgr.getNetworkCapabilities(activeNetwork)
    
    return when {
        caps?.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) == true -> {
            val wifiInfo = connectivityMgr.getNetworkInfo(ConnectivityManager.TYPE_WIFI)
            "WiFi6E (${wifiInfo?.extraInfo ?: "unknown"})"
        }
        caps?.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) == true -> {
            val tm = context.getSystemService<TelephonyManager>()
            when (tm?.dataNetworkType) {
                TelephonyManager.NETWORK_TYPE_NR -> "5G (mmWave/FR2)"
                TelephonyManager.NETWORK_TYPE_LTE -> "LTE (fallback)"
                else -> "Cellular (unknown)"
            }
        }
        else -> "Offline"
    }
}
```

---

### 5. Fallback Protocol: MQTT QoS 2 (Operator Offline Mode)

**When WiFi/5G Unavailable:**

```
Operator's Phone
    (cached commands)
              ↓
    MQTT Broker (mosquitto)
    ├─ Topic: robot/cmd/{robot_id}/operator/{operator_id}
    ├─ QoS: 2 (exactly-once delivery)
    ├─ Retained: false
    └─ TTL: 1 hour
              ↓
    ROV Re-Surfaces
    ├─ Reconnects to MQTT
    ├─ Downloads pending commands
    └─ Executes + ACKs
```

---

## Implementation Roadmap

### Phase 1: MVP (Weeks 1–2)

**Deliverables:**
- ✅ GrapheneOS-compatible Kotlin app skeleton
- ✅ Certificate pinning for mTLS
- ✅ WebSocket client (OkHttp3 + scarlet)
- ✅ Telemetry display (dashboard UI with Jetpack Compose)
- ⚠️ No video streaming yet (add Phase 2)

**Testing:**
- Unit tests (mocking cloud server)
- Emulator tests (Android Emulator runs GrapheneOS)
- Device tests (real Pixel 10 Pro XL if available)

### Phase 2: Video + PointPillars (Weeks 3–4)

**Deliverables:**
- H.264 video decoding (ExoPlayer)
- ML inference: PointPillars 3D object detection
- AR overlay on camera feed (TensorFlow Lite)
- Band-switching logic (WiFi 6E ↔ 5G)

### Phase 3: Hardening (Weeks 5–6)

**Deliverables:**
- Certificate rotation (refresh certs every 90 days)
- Replay attack protection (timestamp validation)
- Rate limiting (DDoS protection)
- Logging (no PII, local storage only)

---

## Security Considerations

### Threat Model

| Threat | Mitigation |
|--------|-----------|
| **Man-in-the-Middle (MitM)** | mTLS + certificate pinning + OCSP stapling |
| **Relay Attack (UWB spoofing)** | Physical distance verification (ToF measurement) |
| **Command Injection** | Input validation + Protobuf schema enforcement |
| **Rogue AP (WiFi spoofing)** | Certificate pinning (not AP SSID matching) |
| **Side-Channel (Timing)** | Constant-time crypto operations (libsodium) |
| **Physical Theft** | Device encryption (GrapheneOS default: AES-256-XTS) |

---

## API Endpoints (RESTful Bootstrap)

**Base:** `https://api.vktest-cloud.lab767.com/v1`

### Provisioning

```
POST /provision
Body: {
  device_token: "jwt_one_time_use",
  public_key: "ed25519_base64",
  fingerprint: "device_hardware_id"
}
Response: {
  client_certificate: "pem_encoded",
  certificate_chain: "pem_encoded",
  ca_bundle: "pem_encoded"
}
```

### Authentication Status (ping)

```
GET /auth/status
Headers: Authorization: mTLS (via certificate)
Response: {
  authenticated: true,
  expires_at: "2027-07-11T12:00:00Z",
  robot_id: "rov-001",
  operator_id: "op-lab767"
}
```

---

## Database Schema (Cloud-Side)

### Operators Table

```sql
CREATE TABLE operators (
  operator_id TEXT PRIMARY KEY,
  pixel_device_id TEXT UNIQUE,  -- Hardware fingerprint
  certificate_fingerprint TEXT,  -- SHA256(public_cert)
  public_key BYTEA,              -- Ed25519 public key
  created_at TIMESTAMP,
  last_authenticated_at TIMESTAMP,
  is_active BOOLEAN DEFAULT true
);
```

### Operation Log

```sql
CREATE TABLE operation_sessions (
  session_id UUID PRIMARY KEY,
  operator_id TEXT REFERENCES operators,
  robot_id TEXT,
  started_at TIMESTAMP,
  ended_at TIMESTAMP,
  total_commands INT,
  total_telemetry_frames INT,
  network_primary TEXT,  -- 'wifi6e' | '5g' | 'mqtt'
  video_stream_active BOOLEAN DEFAULT false
);
```

---

## Deployment Checklist

- [ ] GrapheneOS 2026-07 installed on Pixel 10 Pro XL
- [ ] F-Droid repository enabled (alternative app store)
- [ ] VKTEST app downloaded + verified signature
- [ ] QR provisioning code scanned
- [ ] Cloud certificate installed + verified
- [ ] WiFi 6E network connected (or 5G available)
- [ ] First telemetry frame received (10 Hz)
- [ ] Dashboard displays robot status
- [ ] Command latency <100 ms verified
- [ ] Video stream (if enabled) at 30 fps
- [ ] MQTT fallback tested (turn off WiFi)
- [ ] Permission grants audited (no location unless homing enabled)

---

## Next Steps

1. **Week 1:** Finalize Kotlin boilerplate + CI/CD pipeline
2. **Week 2:** Implement mTLS handshake + WebSocket client
3. **Week 3:** Dashboard UI (Jetpack Compose) + real data integration
4. **Week 4:** Video decoding + PointPillars ML inference
5. **Week 5:** Security hardening + penetration testing
6. **Week 6:** Field deployment + operator training

---

## References

- GrapheneOS Architecture: https://grapheneos.org/articles/
- Android Keystore: https://developer.android.com/training/articles/keystore
- Jetpack Compose: https://developer.android.com/jetpack/compose
- mTLS Best Practices: https://www.cloudflare.com/learning/access-management/what-is-mutual-tls/
- WebSocket Protocol (RFC 6455): https://tools.ietf.org/html/rfc6455
- Protobuf: https://developers.google.com/protocol-buffers

---

**Document Status:** DRAFT → READY FOR DEVELOPMENT  
**Owner:** System Architect  
**Last Updated:** 2026-07-11

