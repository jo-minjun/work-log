import Foundation
import WorkLogCore

func checkDailySettings() {
    let empty = try? JSONDecoder().decode(AppSettings.self, from: Data("{\"version\": 1}".utf8))
    check(empty?.daily == AppSettings.DailySettings(), "daily settings: a file without the group gives defaults")
    let url = tempDir().appendingPathComponent("settings.json")
    var settings = AppSettings.defaults
    settings.daily.githubAccounts = ["work-account"]
    settings.daily.jiraMcpServer = "atlassian"
    do {
        try SettingsStore.save(settings, to: url)
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
        let daily = raw?["daily"] as? [String: Any]
        check(daily?["githubAccounts"] as? [String] == ["work-account"] && daily?["jiraMcpServer"] as? String == "atlassian",
              "daily settings: save writes the group with the collector's key names")
        check(try SettingsStore.load(url).daily == settings.daily, "daily settings: loads back")
    } catch {
        check(false, "daily settings save (\(error))")
    }
}

func checkDailyStoreLatest() {
    let dir = tempDir()
    let fixture = repoRoot.appendingPathComponent("fixtures/daily.json")
    check(DailyStore.latest(dir) == nil, "daily store: an empty folder has no daily")
    do {
        try FileManager.default.copyItem(at: fixture, to: dir.appendingPathComponent("2026-11-02.json"))
        let older = try String(contentsOf: fixture, encoding: .utf8).replacingOccurrences(of: "\"2026-11-02\"", with: "\"2026-10-30\"")
        try older.write(to: dir.appendingPathComponent("2026-10-30.json"), atomically: true, encoding: .utf8)
        try "{broken".write(to: dir.appendingPathComponent("2026-11-03.json"), atomically: true, encoding: .utf8)
        try "{\"startedAt\": \"a\", \"endedAt\": \"b\", \"trigger\": \"app\", \"result\": \"timeout\", \"reason\": \"Timed out after 900s\"}"
            .write(to: dir.appendingPathComponent(DailyStore.lastRunName), atomically: true, encoding: .utf8)
    } catch {
        check(false, "daily store setup (\(error))")
        return
    }
    let daily = DailyStore.latest(dir)
    check(daily?.date == "2026-11-02", "daily store: the newest daily that decodes wins")
    check(daily?.evidence.count == 3 && daily?.evidence[2].weak == true, "daily store: evidence decodes")
    check(daily?.text.hasPrefix("Done (10/30–11/1)\n- Payments\n") == true, "daily store: copy text is kept as written")
    check(daily?.sourceProblems.map(\.source) == ["jira", "standup"], "daily store: sources that are not ok, sorted")
    let run = DailyStore.lastRun(dir)
    check(run?.result == .timeout && run?.succeeded == false && run?.reason == "Timed out after 900s", "daily store: last run decodes")
}

func checkDailyFormat() {
    check(DailyFormat.day("2026-11-02", strings: .en) == "11/2 (Mon)", "daily format: English day")
    check(DailyFormat.day("2026-10-30", strings: .ko) == "10/30 (금)", "daily format: Korean day")
    check(UIStrings.en.dailyTitle(DailyFormat.day("2026-11-02", strings: .en)) == "11/2 (Mon) Daily", "daily format: title")
    check(DailyFormat.time("2026-11-02T10:05:12+09:00", timeZone: TimeZone(identifier: "Asia/Seoul")!) == "10:05",
          "daily format: generated time in the local zone")
}
