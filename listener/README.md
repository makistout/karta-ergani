# erganiOS Card Listener

Lightweight Windows listener v0.3.1 for WRKCardSE jobs only. It does not contain scheduling or punch business rules.

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
The public IP is refreshed independently at startup and every five minutes, then kept in memory/server device state; punch submission performs no IP lookup.
