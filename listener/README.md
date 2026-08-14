# erganiOS Card Listener

Lightweight Windows listener v0.3.9 for WRKCardSE jobs only. It does not contain scheduling or punch business rules.

Job pickup uses an 8-second long-poll cycle with a 2-second retry delay, so a healthy
listener receives newly queued punches within 10 seconds while remaining lightweight.

## Build

```powershell
dotnet publish .\listener\Erganios.Listener\Erganios.Listener.csproj -c Release
```

## Install / configure

1. Create a device from the per-store erganiOS settings.
2. Double-click `erganios-listener.exe`.
3. Fill in the Device ID/token and Ergani credentials.
4. Select **Έλεγχος και αποθήκευση**.
5. Select **Εγκατάσταση υπηρεσίας** and approve the Windows UAC prompt.

The executable copies itself to `C:\Program Files\erganiOS Listener`, registers the
`erganiOSListener` Windows Service with automatic start/recovery, and applies restricted
ACLs to `C:\ProgramData\erganiOS Listener`. Secrets are encrypted using DPAPI LocalMachine.
The setup executable requests administrator elevation so it can always reload and update
the same protected `config.json` used by the Windows Service.
The public IP is resolved independently through `https://api.ipify.org/?format=json` at startup and every five minutes, validated by the backend, then kept in memory/server device state; punch submission performs no IP lookup. The locally resolved IP takes precedence over the server response, and loopback/private addresses are never accepted as public IPs.
