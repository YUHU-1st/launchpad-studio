using System.Text.Json;
using LibreHardwareMonitor.Hardware;

var result = new Dictionary<string, object?> {
    ["CPU"] = null, ["GPU"] = null, ["主板"] = null, ["存储"] = null,
    ["sensors"] = new List<object>()
};

try
{
    var computer = new Computer {
        IsCpuEnabled = true,
        IsGpuEnabled = true,
        IsMotherboardEnabled = true,
        IsMemoryEnabled = true,
        IsStorageEnabled = true
    };
    computer.Open();
    var sensors = (List<object>)result["sensors"]!;
    var groups = new Dictionary<string, List<float>> {
        ["CPU"] = [], ["GPU"] = [], ["主板"] = [], ["存储"] = []
    };

    void ReadHardware(IHardware hardware)
    {
        hardware.Update();
        string group = hardware.HardwareType switch {
            HardwareType.Cpu => "CPU",
            HardwareType.GpuAmd or HardwareType.GpuIntel or HardwareType.GpuNvidia => "GPU",
            HardwareType.Motherboard or HardwareType.SuperIO or HardwareType.EmbeddedController => "主板",
            HardwareType.Storage => "存储",
            _ => ""
        };
        foreach (var sensor in hardware.Sensors)
        {
            if (sensor.SensorType != SensorType.Temperature || sensor.Value is null) continue;
            float value = sensor.Value.Value;
            if (value < 1 || value > 150) continue;
            sensors.Add(new { group, hardware = hardware.Name, name = sensor.Name, value });
            if (groups.ContainsKey(group)) groups[group].Add(value);
        }
        foreach (var sub in hardware.SubHardware) ReadHardware(sub);
    }
    foreach (var hardware in computer.Hardware) ReadHardware(hardware);
    foreach (var pair in groups)
        if (pair.Value.Count > 0) result[pair.Key] = Math.Round(pair.Value.Max(), 1);
    computer.Close();
}
catch (Exception ex)
{
    result["error"] = ex.Message;
}

Console.OutputEncoding = System.Text.Encoding.UTF8;
Console.WriteLine(JsonSerializer.Serialize(result));
