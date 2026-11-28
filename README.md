# Microtek Local Telemetry Reverse Engineering

This project documents how to recover and decrypt telemetry that a Microtek inverter broadcasts locally. It is intended for educational and self-hosted diagnostics use on an inverter you own.

The normal Microtek app does not appear to send this telemetry to a cloud service. Instead, the inverter and app communicate over the local network with an AES-encrypted UDP packet.

## Compatibility
- Luxe WiFi 1200VA (Originally Developed for)
- I-LITHIUM 1500 SW (Confirmed by a redditor)

More Models might be compatible. Let me know if any other model works and I'll add it to the list

Also look at this reddit post, some folks with the same inverters over there: [Stuck on Reverse engineering Microtek Lux Wifi](https://www.reddit.com/r/homelabindia/comments/1y0jho1/stuck_on_reverse_engineering_microtek_lux_wifi/)

> [!WARNING]
> You are handling credentials and device data. Keep the extracted AP password private, do not commit it to Git, and avoid sharing packet captures containing the password or inverter identifiers.

## How the packet works

The device broadcasts UDP packets to port `15951`:

```text
(1.0.0|34:BC:95:B0:86:28|BASE64_ENCRYPTED_PAYLOAD)
```

The unencrypted parts are pipe-separated:

| Field | Meaning |
|---|---|
| Version | Firmware/application packet version |
| MAC | Inverter MAC address |
| Base64 payload | Encrypted JSON telemetry |

The payload is first Base64-decoded and has this structure:

```text
[16-byte IV][AES ciphertext]
```

- Cipher mode: `AES/CBC/NoPadding`
- Key: the internal Wi-Fi/AP password for the inverter
- Key length: Java-style 16-byte key normalization
  - exactly 16 characters: use as-is
  - longer than 16 characters: keep the first 16 characters
  - shorter than 16 characters: pad with NUL (`0x00`) bytes
- Plaintext: JSON, padded with trailing NUL bytes in some observations

Example telemetry:

```json
{
  "rssi": -47,
  "ts": 1795345765326,
  "pow": 1,
  "mode": 2,
  "chrgsts": 3,
  "involt": "239.5",
  "outvolt": "239.5",
  "batvolt": "14.5",
  "load": 0,
  "frequency": "49.6",
  "m_name": "Luxe NEW1400 ",
  "udid": "34ab95b09228",
  "activated": true,
  "wConn": true,
  "bConn": true,
  "_version": "1.0.0",
  "_mac": "34:AB:95:B0:92:28",
  "_ip": "192.168.1.13",
  "_received_at": 1795345765.65648,
  "_age": 2.54528045654297
}
```

The `_version`, `_mac`, `_ip`, `_received_at`, and `_age` fields are added by the listener; they are not contained in the encrypted JSON.

### Telemetry field guide

| Field | Typical meaning |
|---|---|
| `rssi` | Wi-Fi signal strength in dBm |
| `rst` | Reset or device state counter |
| `ts` | Device timestamp in milliseconds |
| `src` | Report source, for example `fpush` |
| `lcmd` | Last command or command state |
| `pow` | Main power/on state |
| `ups` | UPS mode state<br>• `0`: Inverter<br>• `1`: UPS |
| `battypesel` | Selected battery type |
| `buzz` | Buzzer state |
| `mainscut` | Mains cutoff state |
| `highpwr` | High-power mode state |
| `vacation` | Vacation mode state |
| `mode` | Operating mode |
| `chrgsts` | Charging status |
| `involt` | Input voltage |
| `outvolt` | Output voltage |
| `batvolt` | Battery voltage |
| `chrgcurr` | Charging current |
| `load` | Load state or percentage, depending on firmware |
| `chrgtime` | Charging time value |
| `bkptime` | Backup time value |
| `batcolor` | Battery status indicator |
| `turbochrgsts` | Turbo-charge status |
| `battype` | Detected/configured battery type |
| `chrgcurrset` | Configured charging current |
| `fan` | Fan state |
| `mains` | Mains state |
| `cbtripwarn` | Circuit-breaker trip warning |
| `wlevelwarn` | Water-level warning |
| `lowbatwarn` | Low-battery warning |
| `pSliderV` | Primary slider voltage |
| `bkpSliderV` | Backup slider voltage |
| `frequency` | Output/input frequency |
| `dischrgcurr` | Discharge current |
| `m_name` | Model name |
| `i_fv` | Internal firmware identifier |
| `mCoreVer` | Core firmware/version |
| `udid` | Device identifier |
| `fv` | Firmware value |
| `flv` | Firmware/logical version |
| `activated` | Device activation state |
| `wConn` | Wi-Fi connection state |
| `bConn` | Battery connection state |

Names and units can vary by firmware. Treat unfamiliar numeric fields as measurements or state codes rather than assuming a unit.

## Repository layout

| Path | Purpose |
|---|---|
| `test_microtek.py` | Decrypts one manually captured payload |
| `custom-api/app.py` | FastAPI HTTP endpoints |
| `custom-api/microtek.py` | UDP listener and decryption service |
| `custom-api/docker-compose.yaml` | Container configuration and AP password |

## Contents

1. [Prerequisites](#prerequisites)
2. [Extract the AP password](#1-extract-the-ap-password)
3. [Verify packet capture](#2-verify-packet-capture)
4. [Test one payload](#3-test-one-payload)
5. [Run the local API](#4-run-the-local-api)
6. [Troubleshooting](#troubleshooting)
7. [Add sensors to Home Assistant](#5-add-sensors-to-home-assistant)

## Prerequisites

You need:

- An Android device with the Microtek app and a working inverter connection
- A computer on the same network as the inverter
- USB debugging enabled on the Android device
- Android SDK Platform Tools:
  - `adb`
  - `adb logcat`
- Android SDK Build Tools:
  - `zipalign`
  - `apksigner`
- Java `keytool`
- [Apktool](https://apktool.org/docs/install)
- Python 3 and Docker for testing/listening

Confirm the Android tools are on `PATH`:

**PowerShell / Bash:**
```text
adb version
zipalign -version
apksigner --version
keytool -help
```

For command examples below, run PowerShell or Bash in the repository root.

## 1. Extract the AP password

### 1.1 Pull the APK bundle

**Step 1 —** Connect the Android device and confirm it is visible.

**PowerShell / Bash:**
```text
adb devices
```

Unlock the device and accept any USB authorization prompt.

**Step 2 —** Find the APK files for the package.

**PowerShell / Bash:**
```text
adb shell pm path com.microtekdirect.sebz
```

The app is delivered as an APK bundle, so output commonly includes:

```text
package:/data/app/.../base.apk
package:/data/app/.../split_config.arm64_v8a.apk
package:/data/app/.../split_config.xxxhdpi.apk
```

**Step 3 —** Pull every returned APK. Split names vary by device architecture and resources.

**PowerShell / Bash:**
```text
adb pull "/data/app/.../base.apk"
adb pull "/data/app/.../split_config.arm64_v8a.apk"
adb pull "/data/app/.../split_config.xxxhdpi.apk"
```

Replace the example paths with the exact paths printed by `adb shell pm path`. Keep the original file names when pulling them.

### 1.2 Decompile and add a diagnostic log

**Step 1 —** Decompile the base APK.

**PowerShell / Bash:**
```text
apktool d base.apk -o unpack
```

Open `unpack/` in an editor and locate `Thing.smali`. Search for:

- `getAPPassword`
- `Lorg/json/JSONObject;->optString`
- the `"password"` JSON key


Change .locals 2 to .locals 3 at the top of the method, and insert the Log.d call as shown below:
The exact smali layout may differ between app releases.

```smali
.locals 3
.line 278
iget-object v0, p0, Lcom/microtekdirect/sebz/common/models/Thing;->fStack:Lorg/json/JSONObject;
if-eqz v0, :cond_1
const-string v1, "wifi"
invoke-virtual {v0, v1}, Lorg/json/JSONObject;->optJSONObject(Ljava/lang/String;)Lorg/json/JSONObject;
move-result-object v0
if-nez v0, :cond_0
goto :goto_0
.line 279
:cond_0
const-string v1, "password"
invoke-virtual {v0, v1}, Lorg/json/JSONObject;->optString(Ljava/lang/String;)Ljava/lang/String;
move-result-object v0
# --- Start injected logging ---
const-string v2, "MICROTEK_INJECT"
invoke-static {v2, v0}, Landroid/util/Log;->d(Ljava/lang/String;Ljava/lang/String;)I
# --- End injected logging ---
return-object v0
:cond_1
:goto_0
const/4 v0, 0x0
return-object v0
```
Changes Explained:

.locals 3: Increases the local register count from 2 (v0, v1) to 3 (v0, v1, v2). Note that if this method takes parameters (e.g., p0, p1), increasing .locals automatically shifts parameter register numbering in Dalvik bytecode, which apktool handles cleanly on recompile as long as the parameter references (p0) use the p naming convention rather than raw v registers.

const-string v2, "MICROTEK_INJECT": Loads your logcat filter tag into the newly allocated v2 register.

invoke-static {v2, v0}, Landroid/util/Log;->d(...)I: Calls Log.d(tag, msg). Because optString() returns an empty string ("") rather than null when a key is missing, v0 is guaranteed to be a non-null String here, preventing a NullPointerException inside Log.d.

Do not simply copy register numbers between APK versions. Recompile failures or wrong values usually indicate that the smali layout or available registers changed.

### 1.3 Rebuild, align, and sign

**Step 1 —** Rebuild the decompiled APK.

**PowerShell / Bash:**
```text
apktool b unpack -o base_modded.apk
```

**Step 2 —** Create a debug keystore if needed.

**PowerShell / Bash:**
```text
keytool -genkey -v -keystore debug.keystore -storepass android -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000 -dname "CN=Android Debug,O=Android,C=US"
```

**Step 3 —** Align and sign the rebuilt base APK.

**PowerShell / Bash:**
```text
zipalign -v -p 4 base_modded.apk base_aligned.apk
apksigner sign --ks debug.keystore --ks-pass pass:android --key-pass pass:android --out base_signed.apk base_aligned.apk
apksigner verify --verbose base_signed.apk
```

A successful signature verification prints `Verifies`.

**Step 4 —** Sign every split APK with the **same** keystore.

**PowerShell / Bash:**
```text
apksigner sign --ks debug.keystore --ks-pass pass:android --key-pass pass:android --out split_config.arm64_v8a_signed.apk split_config.arm64_v8a.apk
apksigner sign --ks debug.keystore --ks-pass pass:android --key-pass pass:android --out split_config.xxxhdpi_signed.apk split_config.xxxhdpi.apk
```

Repeat one sign command for each split APK file you downloaded. The split names above may differ on your device.

### 1.4 Install the signed bundle

**Step 1 —** Uninstall the original app if its signature differs. This may remove app data.

**PowerShell / Bash:**
```text
adb uninstall com.microtekdirect.sebz
adb install-multiple base_signed.apk split_config.arm64_v8a_signed.apk split_config.xxxhdpi_signed.apk
```

Include exactly one signed APK for every split that belongs to the device. `adb install-multiple` should report `Success`.

**Step 2 —** Start the patched app and **sign back in with the same Microtek account** used before uninstalling/reinstalling. This loads the account's existing inverter pairing.

**Step 3 —** Open or refresh the already-paired inverter (do not add or reset it again), connect the inverter/AP, and monitor the injected tag.

**PowerShell / Bash:**
```text
adb logcat -s MICROTEK_INJECT
```

The password should appear in plaintext in Logcat. Press `Ctrl+C` to stop log capture.

## 2. Verify packet capture

### 2.1 Capture UDP traffic

**Step 1 —** Install a packet capture tool that has permission to inspect UDP traffic.

**Step 2 —** On Linux, run:

**Bash:**
```bash
sudo tcpdump -i any -A -s0 udp port 15951
```

You should see ASCII packets beginning with `(` and containing version, MAC, and a Base64 payload. Capture only the traffic you need.


## 3. Test one payload

### 3.1 Install and run the script

**PowerShell:**
```powershell
py -m pip install cryptography
py test_microtek.py
```

**Bash:**
```bash
python3 -m pip install cryptography
python3 test_microtek.py
```

**Step —** Enter the two requested values:

1. The Wi-Fi/AP password extracted by Logcat
2. Only the Base64 portion, not the version, MAC, parentheses, or the surrounding pipe characters

Example input shape:

```text
IxeXBt6gCrQ...
```

Successful input prints:

- Raw decrypted bytes as hex
- ASCII text
- Parsed JSON

Trailing NUL bytes are expected and are removed for JSON parsing. If you see Base64 decode or JSON errors, verify that you copied the final payload only and that the password is exactly the extracted value.

## 4. Run the local API

### 4.1 Configure the password

**Step 1 —** Set the password in `custom-api/docker-compose.yaml`:

```yaml
environment:
  MICROTEK_PASSWORD: "YOUR_PASSWORD"
```

> [!IMPORTANT]
> Do not commit the real password. Prefer an environment variable or Docker secrets in a private deployment.

### 4.2 Start and inspect the API

**Step 2 —** Start the API.

**PowerShell / Bash:**
```text
cd custom-api
docker compose up -d --build
```

**Step 3 —** Open [http://localhost:8000/](http://localhost:8000/) or query the inverter endpoint.

**PowerShell:**
```powershell
Invoke-RestMethod http://localhost:8000/inverter
```

**Bash:**
```bash
curl http://localhost:8000/inverter
```

The service updates `latest_state` whenever it receives a valid packet and keeps the data until the process restarts. `_age` is the number of seconds since that packet arrived.

## 5. Add sensors to Home Assistant

### 5.1 Add the REST sensor

Create `hass-config/sensors/microtek.yaml` in your Home Assistant configuration directory.

```yaml
- platform: rest
  name: Microtek
  resource: http://your-ip-or-localhost:8000/inverter
  value_template: "{{ value_json.ts }}"
  scan_interval: 6

  json_attributes:
    - rssi
    - pow
    - ups
    - mode
    - buzz
    - chrgsts
    - highpwr
    - turbochrgsts
    - vacation
    - involt
    - outvolt
    - batvolt
    - chrgcurr
    - load
    - chrgtime
    - bkptime
    - frequency
    - dischrgcurr
    - fan
    - mains
    - m_name
    - fv
    - udid

    - lowbatwarn
    - wlevelwarn
    - cbtripwarn
    - chrgrelay_flt
    - outvolt_flt
    - batvolt_flt
    - backfeed_flt
    - transF_temp_flt
    - mosfet_temp_flt
    - shrtckt_flt
    - overload_flt
```

Replace `your-ip-or-localhost` with the IP address of the computer running the local API. Adjust `scan_interval: 6` to suit the update frequency you want.

In `configuration.yaml`, include the directory containing the REST sensor:

```yaml
sensor: !include_dir_merge_list sensors
```

You may need to modify this entry based on your existing Home Assistant configuration structure.

### 5.2 Add template sensors

Open `templates.yaml` and add the following template sensors. The file must already be included by `configuration.yaml` as a template integration.

```yaml
- sensor:
    - name: "UPS Battery"
      unique_id: ups_battery
      device_class: voltage
      state_class: measurement
      unit_of_measurement: "V"
      state: "{{ state_attr('sensor.microtek', 'batvolt') | float(0) }}"

    - name: "UPS Input Voltage"
      unique_id: ups_input_voltage
      device_class: voltage
      state_class: measurement
      unit_of_measurement: "V"
      state: "{{ state_attr('sensor.microtek', 'involt') | float(0) }}"

    - name: "UPS Output Voltage"
      unique_id: ups_output_voltage
      device_class: voltage
      state_class: measurement
      unit_of_measurement: "V"
      state: "{{ state_attr('sensor.microtek', 'outvolt') | float(0) }}"

    - name: "UPS Charge Current"
      unique_id: ups_charge_current
      device_class: current
      state_class: measurement
      unit_of_measurement: "A"
      state: "{{ state_attr('sensor.microtek', 'chrgcurr') | float(0) }}"

    - name: "UPS Discharge Current"
      unique_id: ups_discharge_current
      device_class: current
      state_class: measurement
      unit_of_measurement: "A"
      state: "{{ state_attr('sensor.microtek', 'dischrgcurr') | float(0) }}"

    - name: "UPS Load"
      unique_id: ups_load_perc
      state_class: measurement
      unit_of_measurement: "%"
      state: "{{ state_attr('sensor.microtek', 'load') | int(0) }}"

    - name: "UPS Frequency"
      unique_id: ups_frequency
      device_class: frequency
      state_class: measurement
      unit_of_measurement: "Hz"
      state: "{{ state_attr('sensor.microtek', 'frequency') | float(0) }}"

    - name: "UPS Charge Time"
      unique_id: ups_charge_time
      device_class: duration
      state_class: measurement
      unit_of_measurement: "min"
      state: "{{ state_attr('sensor.microtek', 'chrgtime') | int(0) }}"

    - name: "UPS Backup Time"
      unique_id: ups_backup_time
      device_class: duration
      state_class: measurement
      unit_of_measurement: "min"
      state: "{{ state_attr('sensor.microtek', 'bkptime') | int(0) }}"

    - name: "UPS Charge Power"
      unique_id: ups_charge_power
      device_class: power
      state_class: measurement
      unit_of_measurement: "W"
      state: >
        {{
          (state_attr('sensor.microtek', 'batvolt') | float(0))
          *
          (state_attr('sensor.microtek', 'chrgcurr') | float(0))
        }}

    - name: "UPS Discharge Power"
      unique_id: ups_discharge_power
      device_class: power
      state_class: measurement
      unit_of_measurement: "W"
      state: >
        {{
          (state_attr('sensor.microtek', 'batvolt') | float(0))
          *
          (state_attr('sensor.microtek', 'dischrgcurr') | float(0))
        }}

    - name: "UPS Net Power"
      unique_id: ups_net_power
      device_class: power
      state_class: measurement
      unit_of_measurement: "W"
      state: >
        {{
          (
            states('sensor.ups_charge_power') | float(0)
            -
            states('sensor.ups_discharge_power') | float(0)
          ) | round(1)
        }}

- binary_sensor:
    - name: "UPS Low Battery Warning"
      unique_id: ups_low_battery_warning
      state: "{{ state_attr('sensor.microtek', 'lowbatwarn') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Water Level Warning"
      unique_id: ups_water_level_warning
      state: "{{ state_attr('sensor.microtek', 'wlevelwarn') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS CB Trip Warning"
      unique_id: ups_cb_trip_warning
      state: "{{ state_attr('sensor.microtek', 'cbtripwarn') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Charge Relay Fault"
      unique_id: ups_charge_relay_fault
      state: "{{ state_attr('sensor.microtek', 'chrgrelay_flt') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Output Voltage Fault"
      unique_id: ups_output_voltage_fault
      state: "{{ state_attr('sensor.microtek', 'outvolt_flt') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Battery Voltage Fault"
      unique_id: ups_battery_voltage_fault
      state: "{{ state_attr('sensor.microtek', 'batvolt_flt') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Backfeed Fault"
      unique_id: ups_backfeed_fault
      state: "{{ state_attr('sensor.microtek', 'backfeed_flt') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Transformer Temp Fault"
      unique_id: ups_transformer_temp_fault
      state: "{{ state_attr('sensor.microtek', 'transF_temp_flt') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Mosfet Temp Fault"
      unique_id: ups_mosfet_temp_fault
      state: "{{ state_attr('sensor.microtek', 'mosfet_temp_flt') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Short Circuit Fault"
      unique_id: ups_short_circuit_fault
      state: "{{ state_attr('sensor.microtek', 'shrtckt_flt') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Overload Fault"
      unique_id: ups_overload_fault
      state: "{{ state_attr('sensor.microtek', 'overload_flt') | int(0) == 1 }}"
      device_class: problem

    - name: "UPS Charging"
      unique_id: ups_charging
      state: "{{ state_attr('sensor.microtek', 'chrgcurr') | float(0) > 0 }}"

    - name: "UPS Discharging"
      unique_id: ups_discharging
      state: "{{ state_attr('sensor.microtek', 'dischrgcurr') | float(0) > 0 }}"

    - name: "UPS Fan Running"
      unique_id: ups_fan_running
      state: "{{ state_attr('sensor.microtek', 'fan') | int(0) == 1 }}"
```

### 5.3 Reload and verify

**Step 1 —** In Home Assistant, open **Developer Tools**.

**Step 2 —** Select **YAML** and click **Reload All YAML Configuration**.

If YAML validation reports an error, correct the configuration and reload it again. The REST sensor and its template sensors should then begin updating from the local API.

That is it. Have fun!

