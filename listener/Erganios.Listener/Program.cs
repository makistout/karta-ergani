using System.Diagnostics;
using System.Net.Http.Headers;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.ServiceProcess;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Windows.Forms;

namespace Erganios.Listener;

internal static class Program
{
    internal const string Version = "0.3.1";
    internal const string ServiceName = "erganiOSListener";
    internal static readonly string DataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "erganiOS Listener");
    internal static readonly string ConfigPath = Path.Combine(DataDir, "config.json");

    [STAThread]
    private static void Main(string[] args)
    {
        Directory.CreateDirectory(DataDir);
        if (args.Contains("--install", StringComparer.OrdinalIgnoreCase))
        {
            ServiceInstaller.Install();
            return;
        }
        if (args.Contains("--uninstall", StringComparer.OrdinalIgnoreCase))
        {
            ServiceInstaller.Uninstall();
            return;
        }
        if (args.Contains("--service", StringComparer.OrdinalIgnoreCase))
        {
            ServiceBase.Run(new ListenerWindowsService());
            return;
        }
        ApplicationConfiguration.Initialize();
        Application.Run(new SetupForm());
    }
}

internal sealed class ListenerWindowsService : ServiceBase
{
    private CancellationTokenSource? _stop;
    public ListenerWindowsService() { ServiceName = Program.ServiceName; CanStop = true; AutoLog = true; }
    protected override void OnStart(string[] args)
    {
        _stop = new CancellationTokenSource();
        _ = Task.Run(() => ListenerAgent.RunAsync(_stop.Token));
    }
    protected override void OnStop() { _stop?.Cancel(); }
}

internal sealed class SetupForm : Form
{
    private readonly TextBox _server = new() { Text = "https://erganios.gr" };
    private readonly TextBox _device = new();
    private readonly TextBox _token = new() { UseSystemPasswordChar = true };
    private readonly TextBox _username = new();
    private readonly TextBox _password = new() { UseSystemPasswordChar = true };
    private readonly TextBox _usertype = new() { Text = "02" };
    private readonly TextBox _environment = new() { ReadOnly = true, Enabled = false, Text = "Θα αναγνωριστεί κατά τη σύνδεση" };
    private readonly Label _status = new() { AutoSize = true, Text = "Συμπληρώστε τα στοιχεία pairing και ΕΡΓΑΝΗ." };
    private readonly Button _save = new() { Text = "Έλεγχος και αποθήκευση", AutoSize = true };
    private readonly Button _install = new() { Text = "Εγκατάσταση υπηρεσίας", AutoSize = true };
    private readonly Button _uninstall = new() { Text = "Αφαίρεση υπηρεσίας", AutoSize = true };

    public SetupForm()
    {
        Text = $"erganiOS Listener {Program.Version}";
        Width = 620; Height = 520; StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
        var table = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(18), ColumnCount = 2, RowCount = 10, AutoSize = true };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 170));
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        AddRow(table, 0, "erganiOS URL", _server);
        AddRow(table, 1, "Device ID", _device);
        AddRow(table, 2, "Device Token", _token);
        AddRow(table, 3, "ΕΡΓΑΝΗ username", _username);
        AddRow(table, 4, "ΕΡΓΑΝΗ password", _password);
        AddRow(table, 5, "Usertype", _usertype);
        AddRow(table, 6, "Περιβάλλον Ergani API", _environment);
        var buttons = new FlowLayoutPanel { AutoSize = true, FlowDirection = FlowDirection.LeftToRight };
        buttons.Controls.AddRange([_save, _install, _uninstall]);
        table.Controls.Add(buttons, 0, 7); table.SetColumnSpan(buttons, 2);
        _status.MaximumSize = new Size(550, 0);
        table.Controls.Add(_status, 0, 8); table.SetColumnSpan(_status, 2);
        var note = new Label { AutoSize = true, MaximumSize = new Size(550, 0), Text = "Τα credentials αποθηκεύονται κρυπτογραφημένα με Windows DPAPI.\r\nΗ υπηρεσία ξεκινά αυτόματα με τα Windows." };
        table.Controls.Add(note, 0, 9); table.SetColumnSpan(note, 2);
        Controls.Add(table);
        _save.Click += async (_, _) => await SaveAsync();
        _install.Click += (_, _) => InstallService();
        _uninstall.Click += (_, _) => UninstallService();
        LoadExisting();
        UpdateServiceState();
    }

    private static void AddRow(TableLayoutPanel table, int row, string label, TextBox input)
    {
        input.Dock = DockStyle.Fill;
        table.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left }, 0, row);
        table.Controls.Add(input, 1, row);
    }

    private void LoadExisting()
    {
        if (!File.Exists(Program.ConfigPath)) return;
        try
        {
            var cfg = ListenerConfig.Load();
            _server.Text = cfg.ServerUrl; _device.Text = cfg.DeviceId;
            _token.Text = Dpapi.UnprotectString(cfg.DeviceToken);
            _username.Text = Dpapi.UnprotectString(cfg.ErganiUsername);
            _password.Text = Dpapi.UnprotectString(cfg.ErganiPassword);
            _usertype.Text = cfg.ErganiUsertype;
            _status.Text = "Βρέθηκε υπάρχουσα ρύθμιση.";
        }
        catch (Exception ex) { _status.Text = "Σφάλμα ανάγνωσης ρύθμισης: " + ex.Message; }
    }

    private async Task SaveAsync()
    {
        SetBusy(true, "Έλεγχος erganiOS και credentials ΕΡΓΑΝΗ…");
        try
        {
            var cfg = ListenerConfig.Create(_server.Text, _device.Text, _token.Text, _username.Text, _password.Text, _usertype.Text);
            var connection = await ListenerAgent.VerifyAsync(cfg, CancellationToken.None);
            _environment.Text = $"{connection.EnvironmentLabel} ({connection.Environment})";
            cfg.Save();
            _status.Text = $"Επιτυχής έλεγχος και ασφαλής αποθήκευση. Δημόσια IP: {ListenerAgent.CurrentPublicIp ?? "—"}. Μπορείτε να εγκαταστήσετε την υπηρεσία.";
        }
        catch (Exception ex) { _status.Text = "Αποτυχία: " + ex.Message; }
        finally { SetBusy(false); }
    }

    private void InstallService()
    {
        if (!File.Exists(Program.ConfigPath)) { _status.Text = "Πρώτα εκτελέστε Έλεγχο και αποθήκευση."; return; }
        try
        {
            RunSelfElevated("--install");
            _status.Text = "Η υπηρεσία εγκαταστάθηκε και ξεκίνησε.";
        }
        catch (Exception ex) { _status.Text = "Αποτυχία εγκατάστασης: " + ex.Message; }
        UpdateServiceState();
    }

    private void UninstallService()
    {
        try
        {
            RunSelfElevated("--uninstall");
            _status.Text = "Η υπηρεσία αφαιρέθηκε. Τα κρυπτογραφημένα στοιχεία διατηρήθηκαν.";
        }
        catch (Exception ex) { _status.Text = "Αποτυχία αφαίρεσης: " + ex.Message; }
        UpdateServiceState();
    }

    private static void RunSelfElevated(string arguments)
    {
        var exe = Environment.ProcessPath ?? throw new InvalidOperationException("Executable path missing");
        using var process = Process.Start(new ProcessStartInfo(exe, arguments) { UseShellExecute = true, Verb = "runas", WindowStyle = ProcessWindowStyle.Hidden })
            ?? throw new InvalidOperationException("Δεν ξεκίνησε η εγκατάσταση");
        process.WaitForExit();
        if (process.ExitCode != 0) throw new InvalidOperationException($"Installer error {process.ExitCode}");
    }

    private void UpdateServiceState()
    {
        try
        {
            using var service = new ServiceController(Program.ServiceName);
            _install.Text = service.Status == ServiceControllerStatus.Running ? "Υπηρεσία ενεργή" : "Εκκίνηση/επανεγκατάσταση";
            _uninstall.Enabled = true;
        }
        catch { _install.Text = "Εγκατάσταση υπηρεσίας"; _uninstall.Enabled = false; }
    }
    private void SetBusy(bool busy, string? message = null) { _save.Enabled = !busy; _install.Enabled = !busy; if (message != null) _status.Text = message; UseWaitCursor = busy; }
}

internal static class ServiceInstaller
{
    private static readonly string InstallDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "erganiOS Listener");
    private static readonly string InstalledExe = Path.Combine(InstallDir, "erganios-listener.exe");

    public static void Install()
    {
        try
        {
            Directory.CreateDirectory(InstallDir);
            var source = Environment.ProcessPath ?? throw new InvalidOperationException("Executable path missing");
            Run("sc.exe", ["stop", Program.ServiceName], true);
            Run("sc.exe", ["delete", Program.ServiceName], true);
            Thread.Sleep(750);
            if (!Path.GetFullPath(source).Equals(Path.GetFullPath(InstalledExe), StringComparison.OrdinalIgnoreCase))
                File.Copy(source, InstalledExe, true);
            Run("sc.exe", ["create", Program.ServiceName, "binPath=", $"\"{InstalledExe}\" --service", "start=", "auto", "DisplayName=", "erganiOS Card Listener"]);
            Run("sc.exe", ["description", Program.ServiceName, "WRKCardSE submissions from the business public IP"]);
            Run("sc.exe", ["failure", Program.ServiceName, "reset=", "86400", "actions=", "restart/5000/restart/15000/restart/60000"]);
            Run("icacls.exe", [Program.DataDir, "/inheritance:r", "/grant:r", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F"]);
            Run("sc.exe", ["start", Program.ServiceName]);
        }
        catch (Exception ex)
        {
            try { File.WriteAllText(Path.Combine(Program.DataDir, "install-error.log"), ex.ToString()); } catch { }
            Environment.ExitCode = 1;
        }
    }

    public static void Uninstall()
    {
        try { Run("sc.exe", ["stop", Program.ServiceName], true); Run("sc.exe", ["delete", Program.ServiceName], true); }
        catch { Environment.ExitCode = 1; }
    }

    private static void Run(string file, IEnumerable<string> arguments, bool allowFailure = false)
    {
        var info = new ProcessStartInfo(file) { UseShellExecute = false, CreateNoWindow = true };
        foreach (var argument in arguments) info.ArgumentList.Add(argument);
        using var process = Process.Start(info) ?? throw new InvalidOperationException($"Cannot start {file}");
        process.WaitForExit();
        if (!allowFailure && process.ExitCode != 0) throw new InvalidOperationException($"{file} failed with {process.ExitCode}");
    }
}

internal static class ListenerAgent
{
    private static string? _publicIp;
    public static string? CurrentPublicIp => Volatile.Read(ref _publicIp);

    public static async Task<ListenerConnectionInfo> VerifyAsync(ListenerConfig cfg, CancellationToken ct)
    {
        using var server = ServerClient(cfg, 15);
        using var health = await server.GetAsync(cfg.ServerUrl + "/api/card-listener/v1/health", ct);
        if (!health.IsSuccessStatusCode) throw new InvalidOperationException($"Το pairing απορρίφθηκε (HTTP {(int)health.StatusCode}).");
        var healthJson = JsonNode.Parse(await health.Content.ReadAsStringAsync(ct));
        var environment = healthJson?["ergani_env"]?.GetValue<string>() ?? "unknown";
        var environmentLabel = healthJson?["ergani_env_label"]?.GetValue<string>() ?? environment;
        await RefreshPublicIpOnce(cfg, ct);
        using var ergani = new HttpClient { Timeout = TimeSpan.FromSeconds(30) };
        var auth = await AuthenticateErgani(ergani, cfg, "https://eservices.yeka.gr/WebservicesAPI/Api/", ct);
        if (string.IsNullOrWhiteSpace(auth)) throw new InvalidOperationException("Αποτυχία authentication ΕΡΓΑΝΗ.");
        return new ListenerConnectionInfo(environment, environmentLabel);
    }

    public static async Task RunAsync(CancellationToken ct)
    {
        var networkRefresh = Task.Run(() => RefreshPublicIpLoop(cfgToken: ct), ct);
        var retry = 2;
        try
        {
            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var cfg = ListenerConfig.Load();
                    using var server = ServerClient(cfg, 40);
                    using var response = await server.GetAsync(cfg.ServerUrl + "/api/card-listener/v1/jobs/next?wait=25", ct);
                    if (response.StatusCode == System.Net.HttpStatusCode.Unauthorized) throw new InvalidOperationException("Listener revoked");
                    response.EnsureSuccessStatusCode();
                    var job = JsonNode.Parse(await response.Content.ReadAsStringAsync(ct))?["job"];
                    if (job is not null) await ExecuteJob(job, cfg, server, ct);
                    retry = 2;
                }
                catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
                catch { await Task.Delay(TimeSpan.FromSeconds(retry), ct); retry = Math.Min(30, retry * 2); }
            }
        }
        finally { try { await networkRefresh; } catch (OperationCanceledException) { } }
    }

    private static async Task RefreshPublicIpLoop(CancellationToken cfgToken)
    {
        while (!cfgToken.IsCancellationRequested)
        {
            try { await RefreshPublicIpOnce(ListenerConfig.Load(), cfgToken); }
            catch (OperationCanceledException) when (cfgToken.IsCancellationRequested) { break; }
            catch { }
            await Task.Delay(TimeSpan.FromMinutes(5), cfgToken);
        }
    }

    private static async Task RefreshPublicIpOnce(ListenerConfig cfg, CancellationToken ct)
    {
        using var server = ServerClient(cfg, 15);
        using var response = await server.PostAsync(cfg.ServerUrl + "/api/card-listener/v1/network/refresh", null, ct);
        response.EnsureSuccessStatusCode();
        var ip = JsonNode.Parse(await response.Content.ReadAsStringAsync(ct))?["public_ip"]?.GetValue<string>();
        if (!string.IsNullOrWhiteSpace(ip)) Volatile.Write(ref _publicIp, ip);
    }

    private static HttpClient ServerClient(ListenerConfig cfg, int timeout)
    {
        var client = new HttpClient { Timeout = TimeSpan.FromSeconds(timeout) };
        client.DefaultRequestHeaders.Add("X-Listener-Device", cfg.DeviceId);
        client.DefaultRequestHeaders.Add("X-Listener-Version", Program.Version);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", Dpapi.UnprotectString(cfg.DeviceToken));
        return client;
    }

    private static async Task<string?> AuthenticateErgani(HttpClient client, ListenerConfig cfg, string baseUrl, CancellationToken ct)
    {
        var body = new JsonObject {
            ["Username"] = Dpapi.UnprotectString(cfg.ErganiUsername),
            ["Password"] = Dpapi.UnprotectString(cfg.ErganiPassword),
            ["Usertype"] = cfg.ErganiUsertype
        }.ToJsonString();
        using var response = await client.PostAsync(baseUrl.TrimEnd('/') + "/Authentication", new StringContent(body, Encoding.UTF8, "application/json"), ct);
        var text = await response.Content.ReadAsStringAsync(ct);
        return response.IsSuccessStatusCode ? JsonNode.Parse(text)?["accessToken"]?.GetValue<string>() : null;
    }

    private static async Task ExecuteJob(JsonNode job, ListenerConfig cfg, HttpClient server, CancellationToken ct)
    {
        var id = job["job_uuid"]?.GetValue<string>() ?? throw new InvalidOperationException("Job ID missing");
        var baseUrl = job["ergani_api_base_url"]?.GetValue<string>() ?? throw new InvalidOperationException("Ergani URL missing");
        var payload = job["payload_json"]?.GetValue<string>() ?? throw new InvalidOperationException("Payload missing");
        JsonObject result;
        try
        {
            using var ergani = new HttpClient { Timeout = TimeSpan.FromSeconds(120) };
            var bearer = await AuthenticateErgani(ergani, cfg, baseUrl, ct) ?? throw new InvalidOperationException("Ergani authentication failed");
            using var request = new HttpRequestMessage(HttpMethod.Post, baseUrl.TrimEnd('/') + "/Documents/WRKCardSE") { Content = new StringContent(payload, Encoding.UTF8, "application/json") };
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearer);
            using var response = await ergani.SendAsync(request, ct);
            var text = await response.Content.ReadAsStringAsync(ct);
            var json = JsonNode.Parse(text); var first = json is JsonArray a && a.Count > 0 ? a[0] : json;
            result = new JsonObject { ["success"] = response.IsSuccessStatusCode, ["status"] = response.IsSuccessStatusCode ? "succeeded" : "failed", ["http_status"] = (int)response.StatusCode, ["protocol"] = first?["protocol"]?.DeepClone(), ["ergani_submission_id"] = first?["id"]?.DeepClone(), ["submit_date"] = first?["submitDate"]?.DeepClone(), ["data"] = json?.DeepClone(), ["error"] = response.IsSuccessStatusCode ? null : Safe(text) };
        }
        catch (HttpRequestException ex) { result = new JsonObject { ["success"] = false, ["status"] = "needs_review", ["error_code"] = "network_unknown", ["error"] = Safe(ex.Message) }; }
        catch (Exception ex) { result = new JsonObject { ["success"] = false, ["status"] = "failed", ["error_code"] = "listener_error", ["error"] = Safe(ex.Message) }; }
        var body = result.ToJsonString(); var delay = 2;
        while (!ct.IsCancellationRequested)
        {
            try { using var content = new StringContent(body, Encoding.UTF8, "application/json"); using var callback = await server.PostAsync($"{cfg.ServerUrl}/api/card-listener/v1/jobs/{id}/result", content, ct); callback.EnsureSuccessStatusCode(); return; }
            catch (HttpRequestException) { await Task.Delay(TimeSpan.FromSeconds(delay), ct); delay = Math.Min(30, delay * 2); }
        }
    }
    private static string Safe(string value) => value.Length <= 800 ? value : value[..800];
}

internal sealed record ListenerConfig(string ServerUrl, string DeviceId, string DeviceToken, string ErganiUsername, string ErganiPassword, string ErganiUsertype)
{
    public static ListenerConfig Create(string server, string device, string token, string user, string password, string usertype)
    {
        server = server.Trim().TrimEnd('/');
        if (!Uri.TryCreate(server, UriKind.Absolute, out var uri) || uri.Scheme != "https") throw new InvalidOperationException("Απαιτείται έγκυρο HTTPS URL.");
        _ = Guid.Parse(device.Trim());
        if (string.IsNullOrWhiteSpace(token) || string.IsNullOrWhiteSpace(user) || string.IsNullOrWhiteSpace(password)) throw new InvalidOperationException("Λείπουν υποχρεωτικά στοιχεία.");
        return new(server, device.Trim(), Dpapi.ProtectString(token), Dpapi.ProtectString(user), Dpapi.ProtectString(password), string.IsNullOrWhiteSpace(usertype) ? "02" : usertype.Trim());
    }
    public void Save() { Directory.CreateDirectory(Program.DataDir); File.WriteAllText(Program.ConfigPath, JsonSerializer.Serialize(this, AppJsonContext.Default.ListenerConfig)); }
    public static ListenerConfig Load() => JsonSerializer.Deserialize(File.ReadAllText(Program.ConfigPath), AppJsonContext.Default.ListenerConfig) ?? throw new InvalidOperationException("Invalid configuration");
}

internal sealed record ListenerConnectionInfo(string Environment, string EnvironmentLabel);

internal static class Dpapi
{
    [StructLayout(LayoutKind.Sequential)] private struct Blob { public int Length; public IntPtr Data; }
    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)] private static extern bool CryptProtectData(ref Blob input, string? description, IntPtr entropy, IntPtr reserved, IntPtr prompt, int flags, out Blob output);
    [DllImport("crypt32.dll", SetLastError = true)] private static extern bool CryptUnprotectData(ref Blob input, IntPtr description, IntPtr entropy, IntPtr reserved, IntPtr prompt, int flags, out Blob output);
    [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr memory);
    public static string ProtectString(string value) => Convert.ToBase64String(Transform(Encoding.UTF8.GetBytes(value), true));
    public static string UnprotectString(string value) => Encoding.UTF8.GetString(Transform(Convert.FromBase64String(value), false));
    private static byte[] Transform(byte[] bytes, bool protect)
    {
        var ptr = Marshal.AllocHGlobal(bytes.Length);
        try { Marshal.Copy(bytes, 0, ptr, bytes.Length); var input = new Blob { Length = bytes.Length, Data = ptr }; Blob output; var ok = protect ? CryptProtectData(ref input, "erganiOS Listener", IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 4, out output) : CryptUnprotectData(ref input, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, 4, out output); if (!ok) throw new InvalidOperationException($"DPAPI error {Marshal.GetLastWin32Error()}"); try { var result = new byte[output.Length]; Marshal.Copy(output.Data, result, 0, output.Length); return result; } finally { LocalFree(output.Data); } }
        finally { CryptographicOperations.ZeroMemory(bytes); Marshal.FreeHGlobal(ptr); }
    }
}

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.SnakeCaseLower, WriteIndented = true)]
[JsonSerializable(typeof(ListenerConfig))]
internal partial class AppJsonContext : JsonSerializerContext { }
