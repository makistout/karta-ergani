using System.Diagnostics;
using System.Net.Http.Headers;
using System.Net;
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
    internal const string Version = "0.3.8";
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
    private readonly TextBox _usertype = new() { Text = "01" };
    private readonly TextBox _environment = new() { ReadOnly = true, Enabled = false, Text = "Θα αναγνωριστεί κατά τη σύνδεση" };
    private readonly Label _status = new() { AutoSize = true, Text = "Συμπληρώστε τα στοιχεία pairing και ΕΡΓΑΝΗ." };
    private readonly Label _serviceState = new() { AutoSize = true, Text = "Μη εγκατεστημένη" };
    private readonly Button _save = new() { Text = "Έλεγχος και αποθήκευση", AutoSize = true };
    private readonly Button _install = new() { Text = "Εγκατάσταση υπηρεσίας", AutoSize = true };
    private readonly Button _uninstall = new() { Text = "Αφαίρεση υπηρεσίας", AutoSize = true };

    public SetupForm()
    {
        Text = $"erganiOS Listener {Program.Version}";
        AutoScaleMode = AutoScaleMode.Dpi;
        Font = new Font("Segoe UI", 10F, FontStyle.Regular, GraphicsUnit.Point);
        BackColor = Color.FromArgb(244, 247, 251);
        ForeColor = Color.FromArgb(25, 39, 58);
        ClientSize = new Size(760, 690); MinimumSize = new Size(520, 620);
        StartPosition = FormStartPosition.CenterScreen; AutoScroll = false;
        FormBorderStyle = FormBorderStyle.Sizable; MaximizeBox = true;

        var page = new Panel { Dock = DockStyle.Fill, AutoScroll = true, BackColor = BackColor };
        var content = new TableLayoutPanel {
            Dock = DockStyle.Top, Padding = new Padding(20, 14, 20, 14), ColumnCount = 1,
            AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, BackColor = BackColor
        };
        content.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));

        var header = new Panel { Dock = DockStyle.Top, Height = 96, BackColor = Color.FromArgb(18, 54, 78), Padding = new Padding(28, 14, 28, 10) };
        var title = new Label { Text = "erganiOS Listener", AutoSize = true, ForeColor = Color.White, Font = new Font("Segoe UI Semibold", 19F) };
        var subtitle = new Label { Text = "Ασφαλής τοπική υποβολή ψηφιακής κάρτας", AutoSize = true, ForeColor = Color.FromArgb(190, 219, 235), Font = new Font("Segoe UI", 10F), Location = new Point(31, 52) };
        var version = new Label { Text = $"v{Program.Version}", AutoSize = true, ForeColor = Color.FromArgb(18, 54, 78), BackColor = Color.FromArgb(205, 235, 247), Font = new Font("Segoe UI Semibold", 9F), Padding = new Padding(9, 4, 9, 4), Anchor = AnchorStyles.Top | AnchorStyles.Right };
        header.Controls.Add(title); header.Controls.Add(subtitle); header.Controls.Add(version);
        header.Resize += (_, _) => version.Location = new Point(Math.Max(20, header.ClientSize.Width - version.Width - 28), 18);

        var pairing = CreateSection("Σύνδεση με erganiOS", "Τα στοιχεία pairing συνδέουν αυτή τη συσκευή αποκλειστικά με το συγκεκριμένο κατάστημα.");
        AddRow(pairing, 2, "Διεύθυνση erganiOS", _server);
        AddRow(pairing, 3, "Device ID", _device);
        AddRow(pairing, 4, "Device Token", _token);

        var ergani = CreateSection("Στοιχεία ΕΡΓΑΝΗ", "Χρησιμοποιούνται μόνο τοπικά για την αποστολή WRKCardSE από τη δημόσια IP της επιχείρησης.");
        AddRow(ergani, 2, "Username", _username);
        AddRow(ergani, 3, "Password", _password);
        AddRow(ergani, 4, "Usertype", _usertype);
        AddRow(ergani, 5, "Ergani API", _environment);

        StyleInput(_server); StyleInput(_device); StyleInput(_token); StyleInput(_username);
        StyleInput(_password); StyleInput(_usertype); StyleInput(_environment);
        _environment.BackColor = Color.FromArgb(239, 243, 247);

        StyleButton(_save, Color.FromArgb(30, 126, 166), Color.White);
        StyleButton(_install, Color.FromArgb(28, 145, 104), Color.White);
        StyleButton(_uninstall, Color.FromArgb(235, 241, 246), Color.FromArgb(60, 76, 93));
        var buttons = new FlowLayoutPanel { AutoSize = true, FlowDirection = FlowDirection.LeftToRight, WrapContents = true, Dock = DockStyle.Fill, Margin = new Padding(0, 4, 0, 8), BackColor = BackColor };
        buttons.Controls.AddRange([_save, _install, _uninstall]);

        var statusCard = new TableLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, ColumnCount = 2, Padding = new Padding(16, 10, 16, 10), BackColor = Color.FromArgb(231, 243, 250), Margin = new Padding(0, 2, 0, 5) };
        statusCard.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        statusCard.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        _status.ForeColor = Color.FromArgb(23, 83, 112); _status.Font = new Font("Segoe UI Semibold", 9.5F); _status.Dock = DockStyle.Fill; _status.MaximumSize = new Size(570, 0);
        _serviceState.ForeColor = Color.FromArgb(87, 101, 115); _serviceState.BackColor = Color.White; _serviceState.Font = new Font("Segoe UI Semibold", 9F); _serviceState.Padding = new Padding(9, 5, 9, 5); _serviceState.Margin = new Padding(14, 0, 0, 0);
        statusCard.Controls.Add(_status, 0, 0); statusCard.Controls.Add(_serviceState, 1, 0);

        var note = new Label { AutoSize = true, Dock = DockStyle.Fill, ForeColor = Color.FromArgb(91, 105, 120), Font = new Font("Segoe UI", 9F), Margin = new Padding(2, 5, 2, 0), Text = "🔒 Τα credentials αποθηκεύονται κρυπτογραφημένα με Windows DPAPI.\r\nΗ υπηρεσία ξεκινά αυτόματα με τα Windows." };

        content.Controls.Add(pairing); content.Controls.Add(ergani); content.Controls.Add(buttons); content.Controls.Add(statusCard); content.Controls.Add(note);
        page.Controls.Add(content); page.Controls.Add(header); Controls.Add(page);
        AcceptButton = _save;
        Shown += (_, _) => FitToWorkingArea();
        _save.Click += async (_, _) => await SaveAsync();
        _install.Click += (_, _) => InstallService();
        _uninstall.Click += (_, _) => UninstallService();
        LoadExisting();
        UpdateServiceState();
    }

    private void FitToWorkingArea()
    {
        var work = Screen.FromControl(this).WorkingArea;
        Size = new Size(Math.Min(Width, Math.Max(MinimumSize.Width, work.Width - 24)), Math.Min(Height, Math.Max(MinimumSize.Height, work.Height - 24)));
        Location = new Point(work.Left + Math.Max(0, (work.Width - Width) / 2), work.Top + Math.Max(0, (work.Height - Height) / 2));
    }

    private static TableLayoutPanel CreateSection(string title, string subtitle)
    {
        var table = new TableLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, AutoSizeMode = AutoSizeMode.GrowAndShrink, ColumnCount = 2, Padding = new Padding(18, 12, 18, 12), BackColor = Color.White, Margin = new Padding(0, 0, 0, 10) };
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 190));
        table.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        var heading = new Label { Text = title, AutoSize = true, Font = new Font("Segoe UI Semibold", 12F), ForeColor = Color.FromArgb(24, 55, 75), Margin = new Padding(0, 0, 0, 3) };
        var description = new Label { Text = subtitle, AutoSize = true, Dock = DockStyle.Fill, ForeColor = Color.FromArgb(96, 111, 126), Font = new Font("Segoe UI", 8.8F), Margin = new Padding(0, 0, 0, 8), MaximumSize = new Size(620, 0) };
        table.Controls.Add(heading, 0, 0); table.SetColumnSpan(heading, 2);
        table.Controls.Add(description, 0, 1); table.SetColumnSpan(description, 2);
        return table;
    }

    private static void AddRow(TableLayoutPanel table, int row, string label, TextBox input)
    {
        input.Dock = DockStyle.Fill;
        input.Margin = new Padding(8, 3, 0, 4);
        table.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left, ForeColor = Color.FromArgb(51, 68, 84), Font = new Font("Segoe UI Semibold", 9.3F), Margin = new Padding(0, 7, 8, 4) }, 0, row);
        table.Controls.Add(input, 1, row);
    }

    private static void StyleInput(TextBox input)
    {
        input.Font = new Font("Segoe UI", 10F); input.BorderStyle = BorderStyle.FixedSingle;
        input.BackColor = Color.White; input.ForeColor = Color.FromArgb(26, 42, 58);
    }

    private static void StyleButton(Button button, Color background, Color foreground)
    {
        button.FlatStyle = FlatStyle.Flat; button.FlatAppearance.BorderSize = 0;
        button.BackColor = background; button.ForeColor = foreground;
        button.Font = new Font("Segoe UI Semibold", 9.4F); button.Padding = new Padding(12, 5, 12, 5);
        button.Margin = new Padding(0, 0, 9, 0); button.Cursor = Cursors.Hand;
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
            SetStatus($"Φορτώθηκε η αποθηκευμένη ρύθμιση από {Program.ConfigPath}.", true);
        }
        catch (Exception ex) { SetStatus("Σφάλμα ανάγνωσης ρύθμισης: " + ex.Message, false); }
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
            if (!File.Exists(Program.ConfigPath)) throw new IOException("Το αρχείο ρύθμισης δεν δημιουργήθηκε.");
            SetStatus($"Επιτυχής έλεγχος και ασφαλής αποθήκευση. Δημόσια IP: {ListenerAgent.CurrentPublicIp ?? "—"}. Μπορείτε να εγκαταστήσετε την υπηρεσία.", true);
        }
        catch (Exception ex) { SetStatus("Αποτυχία: " + ex.Message, false); }
        finally { SetBusy(false); }
    }

    private void InstallService()
    {
        if (!File.Exists(Program.ConfigPath)) { SetStatus("Πρώτα εκτελέστε Έλεγχο και αποθήκευση.", false); return; }
        try
        {
            RunSelfElevated("--install");
            SetStatus("Η υπηρεσία εγκαταστάθηκε και ξεκίνησε.", true);
        }
        catch (Exception ex) { SetStatus("Αποτυχία εγκατάστασης: " + ex.Message, false); }
        UpdateServiceState();
    }

    private void UninstallService()
    {
        try
        {
            RunSelfElevated("--uninstall");
            SetStatus("Η υπηρεσία αφαιρέθηκε. Τα κρυπτογραφημένα στοιχεία διατηρήθηκαν.", true);
        }
        catch (Exception ex) { SetStatus("Αποτυχία αφαίρεσης: " + ex.Message, false); }
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
            _serviceState.Text = service.Status == ServiceControllerStatus.Running ? "● Online" : "● Εγκατεστημένη";
            _serviceState.ForeColor = service.Status == ServiceControllerStatus.Running ? Color.FromArgb(24, 132, 91) : Color.FromArgb(184, 116, 20);
            _uninstall.Enabled = true;
        }
        catch { _install.Text = "Εγκατάσταση υπηρεσίας"; _serviceState.Text = "Μη εγκατεστημένη"; _serviceState.ForeColor = Color.FromArgb(87, 101, 115); _uninstall.Enabled = false; }
    }
    private void SetStatus(string message, bool? success = null)
    {
        _status.Text = message;
        _status.ForeColor = success switch
        {
            true => Color.FromArgb(21, 112, 78),
            false => Color.FromArgb(176, 54, 54),
            _ => Color.FromArgb(23, 83, 112),
        };
    }
    private void SetBusy(bool busy, string? message = null) { _save.Enabled = !busy; _install.Enabled = !busy; if (message != null) SetStatus(message); UseWaitCursor = busy; }
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
        string? publicIp = null;
        try
        {
            using var lookup = new HttpClient { Timeout = TimeSpan.FromSeconds(10) };
            var json = JsonNode.Parse(await lookup.GetStringAsync("https://api.ipify.org/?format=json", ct));
            publicIp = NormalizePublicIp(json?["ip"]?.GetValue<string>());
        }
        catch { }
        using var server = ServerClient(cfg, 15);
        using var content = new StringContent(JsonSerializer.Serialize(new { public_ip = publicIp }), Encoding.UTF8, "application/json");
        using var response = await server.PostAsync(cfg.ServerUrl + "/api/card-listener/v1/network/refresh", content, ct);
        response.EnsureSuccessStatusCode();
        var serverIp = NormalizePublicIp(JsonNode.Parse(await response.Content.ReadAsStringAsync(ct))?["public_ip"]?.GetValue<string>());
        Volatile.Write(ref _publicIp, publicIp ?? serverIp);
    }

    private static string? NormalizePublicIp(string? candidate)
    {
        if (!IPAddress.TryParse((candidate ?? "").Trim(), out var ip)) return null;
        if (IPAddress.IsLoopback(ip) || ip.Equals(IPAddress.Any) || ip.Equals(IPAddress.IPv6Any) || ip.IsIPv6LinkLocal) return null;
        if (ip.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)
        {
            var b = ip.GetAddressBytes();
            if (b[0] == 10 || b[0] == 127 || (b[0] == 169 && b[1] == 254) ||
                (b[0] == 172 && b[1] >= 16 && b[1] <= 31) || (b[0] == 192 && b[1] == 168) ||
                (b[0] == 100 && b[1] >= 64 && b[1] <= 127)) return null;
        }
        return ip.ToString();
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
        return new(server, device.Trim(), Dpapi.ProtectString(token), Dpapi.ProtectString(user), Dpapi.ProtectString(password), string.IsNullOrWhiteSpace(usertype) ? "01" : usertype.Trim());
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
