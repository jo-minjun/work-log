import Foundation
import WorkLogCore

func checkSettingsSaveKeepsForeignKeys() {
    let url = tempDir().appendingPathComponent("settings.json")
    writeJSON("""
    {"version": 1, "provider": "claude", "slack": {"userId": "UX1", "displayName": "Someone", "checkedAt": null}, "futureKey": [1, 2]}
    """, to: url)
    var settings = AppSettings.defaults
    settings.provider = .codex
    settings.schedule.interval.hours = 7
    do {
        try SettingsStore.save(settings, to: url)
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        let slack = raw["slack"] as? [String: Any]
        check(slack?["userId"] as? String == "UX1" && slack?["displayName"] as? String == "Someone" && slack?["checkedAt"] is NSNull,
              "settings save: slack block is kept as written")
        check(sameJSON(raw["futureKey"], [1, 2]), "settings save: unknown keys are kept")
        check(raw["provider"] as? String == "codex" && raw["notifyOnSuccess"] as? Bool == true && raw["logLanguage"] as? String == "en",
              "settings save: app-owned keys are written")
        let leftovers = try FileManager.default.contentsOfDirectory(atPath: url.deletingLastPathComponent().path)
        check(leftovers == ["settings.json"], "settings save: no temp file left behind")
        check(try SettingsStore.load(url).schedule.interval.hours == 7, "settings save: loads back")
    } catch {
        check(false, "settings save keeps foreign keys (\(error))")
    }
}

func checkSettingsLoadMissingAndBroken() {
    let dir = tempDir()
    let url = dir.appendingPathComponent("settings.json")
    check((try? SettingsStore.load(url)) == AppSettings.defaults, "settings load: missing file gives defaults")
    writeJSON("{not json", to: url)
    check((try? SettingsStore.load(url)) == nil, "settings load: broken file throws")
    check((try? SettingsStore.save(.defaults, to: url)) == nil, "settings save: refuses to overwrite a broken file")
    try? SettingsStore.save(.defaults, to: dir.appendingPathComponent("new/settings.json"))
    check(FileManager.default.fileExists(atPath: dir.appendingPathComponent("new/settings.json").path), "settings save: creates a missing file")
}

func checkAppLanguageSetting() {
    let url = tempDir().appendingPathComponent("settings.json")
    writeJSON("{\"version\": 1, \"logLanguage\": \"ko\"}", to: url)
    let loaded = try? SettingsStore.load(url)
    check(loaded?.appLanguage == .en && loaded?.logLanguage == .ko, "app language: a missing key is English, independent of the log language")
    writeJSON("{\"slack\": {\"userId\": \"UX1\", \"displayName\": \"Someone\", \"checkedAt\": null}}", to: url)
    var settings = AppSettings.defaults
    settings.appLanguage = .ko
    do {
        try SettingsStore.save(settings, to: url)
        let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as! [String: Any]
        check(raw["appLanguage"] as? String == "ko" && raw["logLanguage"] as? String == "en", "app language: saved as its own key")
        check((raw["slack"] as? [String: Any])?["userId"] as? String == "UX1", "app language: save keeps the slack block")
        let again = try SettingsStore.load(url)
        check(again.appLanguage == .ko && again.logLanguage == .en, "app language: ko round-trips")
    } catch {
        check(false, "app language save and load (\(error))")
    }
}

func checkKoreanDisplayText() {
    let ko = UIStrings.ko
    let cal = calendar()
    let now = date(cal, 2026, 10, 29, 14, 46)
    check(DisplayText.nextRun(date(cal, 2026, 10, 29, 22, 0), now: now, strings: ko, calendar: cal) == "다음 실행 22:00", "ko text: next run today")
    check(DisplayText.nextRun(date(cal, 2026, 10, 30, 10, 0), now: now, strings: ko, calendar: cal) == "다음 실행 금 10:00", "ko text: next run on another day")
    check(DisplayText.updatedAgo(now.addingTimeInterval(-180), now: now, strings: ko) == "3분 전 갱신", "ko text: minutes ago")
    check(DisplayText.resetsIn(now.addingTimeInterval(3 * 3600 + 42 * 60 + 30), now: now, strings: ko) == "초기화까지 3시간 42분", "ko text: resets in")
    check(NotificationText.newSuggestions(3, strings: ko).title == "새 제안 3건", "ko text: new suggestions notification")
}

func checkBrokenFileBackUp() {
    let url = tempDir().appendingPathComponent("suggestions.json")
    writeJSON("{broken", to: url)
    let seoul = TimeZone(identifier: "Asia/Seoul")!
    let now = date(calendar(), 2026, 10, 29, 14, 46).addingTimeInterval(7)
    let target = try? BrokenFile.backUp(url, now: now, timeZone: seoul)
    check(target?.lastPathComponent == "suggestions.json.broken-20261029-144607", "backup: name carries the timestamp")
    check(!FileManager.default.fileExists(atPath: url.path) && (try? String(contentsOf: target!, encoding: .utf8)) == "{broken",
          "backup: original is moved, content kept")
}

func checkSlotDecision() {
    let slot = Date(timeIntervalSince1970: 1_000_000)
    check(SlotDecision.decide(slot: slot, firedAt: slot.addingTimeInterval(5), isRunning: false) == .run, "slot: on time runs")
    check(SlotDecision.decide(slot: slot, firedAt: slot.addingTimeInterval(300), isRunning: false) == .skip(reason: "Slot passed"),
          "slot: late is skipped as passed")
    check(SlotDecision.decide(slot: slot, firedAt: slot, isRunning: true) == .skip(reason: "Previous run in progress"),
          "slot: during a run is skipped")
}

func runRecord(_ result: RunRecord.Result, at seconds: TimeInterval, reason: String? = nil, cost: Double? = nil, tokens: Int? = nil) -> RunRecord {
    let start = Date(timeIntervalSince1970: seconds)
    return RunRecord(startedAt: start, endedAt: start, trigger: .schedule, provider: .claude, result: result,
                     reason: reason, costUsd: cost, tokens: tokens)
}

func checkLastRunIgnoresSkipped() {
    let runs = [runRecord(.succeeded, at: 100), runRecord(.failed, at: 200), runRecord(.skipped, at: 300, reason: "Slot passed")]
    check(RunOutcome.lastRun(runs)?.startedAt == Date(timeIntervalSince1970: 200), "last run: skipped lines are passed over")
    check(RunOutcome.lastRunMark(runs) == .failure, "last run: failure mark survives a later skip")
    check(RunOutcome.lastRunMark(runs + [runRecord(.succeeded, at: 400)]) == .none, "last run: success clears the mark")
    check(RunOutcome.lastRunMark([runRecord(.skipped, at: 1)]) == .none, "last run: only skips means no mark")
}

func checkWarningsMark() {
    let warned = runRecord(.succeeded, at: 500, reason: "Completed with warnings", cost: 0.97)
    check(RunOutcome.lastRunMark([runRecord(.failed, at: 100), warned]) == .warning, "warnings: last run with warnings gets the warning mark")
    check(RunOutcome.lastRunMark([warned, runRecord(.succeeded, at: 600)]) == .none, "warnings: a clean run clears it")
    check(NotificationText.afterRun(warned, notifyOnSuccess: true, strings: .en)?.title == "Collection finished with warnings · $0.97",
          "warnings: success notification says so")
    check(NotificationText.afterRun(warned, notifyOnSuccess: false, strings: .en) == nil, "warnings: follows the success notification setting")
}

func checkAppFailureRecord() {
    let at = Date(timeIntervalSince1970: 1_793_000_000)
    let record = RunRecord.appFailure(trigger: .schedule, provider: .codex, startedAt: at, endedAt: at.addingTimeInterval(5),
                                      reason: "run.sh not found")
    check(record.result == .failed && record.reason == "run.sh not found" && record.logPath == nil && record.costUsd == nil
          && record.provider == .codex && record.trigger == .schedule, "app failure: record fields")
    check(NotificationText.afterRun(record, notifyOnSuccess: false, strings: .en) == NotificationText(title: "Collection failed", body: "run.sh not found"),
          "app failure: posts Collection failed")
    check(RunRecord.stoppedOnQuitReason == "Stopped on quit", "app failure: quit reason text")
}

func checkRunRecordForSpawn() {
    let spawned = Date(timeIntervalSince1970: 1000.4)
    let ownSkip = runRecord(.skipped, at: 1200, reason: "Previous run in progress")
    let runs = [runRecord(.succeeded, at: 900), runRecord(.succeeded, at: 1000, cost: 0.5), ownSkip]
    check(RunOutcome.record(runs, spawnedAt: spawned)?.costUsd == 0.5, "spawn record: run.sh line found, app skip ignored")
    let busy = runRecord(.skipped, at: 1001, reason: "Another run is in progress")
    check(RunOutcome.record(runs + [busy], spawnedAt: spawned) == busy, "spawn record: run.sh skip counts")
    check(RunOutcome.record([runRecord(.succeeded, at: 900)], spawnedAt: spawned) == nil, "spawn record: older lines are not this run")
}

func checkNewPendingCount() {
    check(RunOutcome.newPendingCount(previous: nil, current: ["a", "b"]) == 0, "pending: first load is the baseline")
    check(RunOutcome.newPendingCount(previous: ["a"], current: ["a", "b", "c"]) == 2, "pending: growth counts new ids")
    check(RunOutcome.newPendingCount(previous: ["a"], current: ["b"]) == 1, "pending: answered one, new one arrived")
    check(RunOutcome.newPendingCount(previous: ["a", "b"], current: ["a"]) == 0, "pending: shrinking posts nothing")
}

func checkNotificationText() {
    check(NotificationText.afterRun(runRecord(.succeeded, at: 0, cost: 0.97), notifyOnSuccess: true, strings: .en)?.title == "Collection finished · $0.97",
          "notify: claude success shows cost")
    check(NotificationText.afterRun(runRecord(.succeeded, at: 0, tokens: 12345), notifyOnSuccess: true, strings: .en)?.title == "Collection finished · 12,345 tokens",
          "notify: codex success shows tokens")
    check(NotificationText.afterRun(runRecord(.succeeded, at: 0, cost: 0.97), notifyOnSuccess: false, strings: .en) == nil, "notify: success can be turned off")
    check(NotificationText.afterRun(runRecord(.failed, at: 0, reason: "Timed out"), notifyOnSuccess: false, strings: .en)
          == NotificationText(title: "Collection failed", body: "Timed out"), "notify: failure always posts")
    check(NotificationText.afterRun(runRecord(.skipped, at: 0, reason: "x"), notifyOnSuccess: true, strings: .en) == nil, "notify: skipped posts nothing")
    check(NotificationText.newSuggestions(3, strings: .en).title == "3 new suggestions", "notify: new suggestions count")
}

func checkDisplayText() {
    let now = Date(timeIntervalSince1970: 100_000)
    check(DisplayText.updatedAgo(now.addingTimeInterval(-180), now: now, strings: .en) == "updated 3 min ago", "text: updated minutes ago")
    check(DisplayText.updatedAgo(now.addingTimeInterval(-3 * 3600 - 10), now: now, strings: .en) == "updated 3 h ago", "text: updated hours ago")
    check(DisplayText.resetsIn(now.addingTimeInterval(3 * 3600 + 42 * 60 + 30), now: now, strings: .en) == "Resets in 3h 42m", "text: resets in hours")
    check(DisplayText.resetsIn(now.addingTimeInterval(4 * 86400 + 20 * 3600 + 60), now: now, strings: .en) == "Resets in 4d 20h", "text: resets in days")
    check(DisplayText.cost(12.4) == "$12.40" && DisplayText.runs(1, strings: .en) == "1 run" && DisplayText.runs(14, strings: .en) == "14 runs", "text: cost and run count")
}

// Waits briefly for a process to disappear; kill(pid, 0) fails with ESRCH once it is gone and reaped.
func processGone(_ pid: pid_t, within seconds: Double) -> Bool {
    let deadline = Date().addingTimeInterval(seconds)
    while Date() < deadline {
        if kill(pid, 0) != 0 && errno == ESRCH { return true }
        usleep(50_000)
    }
    return false
}

func checkProcessGroupTerminate() {
    let dir = tempDir()
    let pidFile = dir.appendingPathComponent("grandchild.pid").path
    let script = "sleep 60 & echo $! > '\(pidFile)'; wait"
    do {
        let pid = try ProcessGroup.spawn("/bin/zsh", arguments: ["-c", script], environment: ["PATH": "/bin:/usr/bin"],
                                         outputPath: dir.appendingPathComponent("out.log").path)
        check(getpgid(pid) == pid, "process group: child leads its own group")
        var grandchild: pid_t = 0
        let deadline = Date().addingTimeInterval(5)
        while grandchild == 0 && Date() < deadline {
            grandchild = pid_t((try? String(contentsOfFile: pidFile, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "") ?? 0
            usleep(50_000)
        }
        check(grandchild > 0 && getpgid(grandchild) == pid, "process group: grandchild joins the group")
        ProcessGroup.terminate(pid)
        let code = ProcessGroup.wait(pid)
        check(code == 128 + SIGTERM, "process group: child ends by SIGTERM (got \(code))")
        // The orphaned sleep is reparented to launchd, which reaps it.
        check(grandchild > 0 && processGone(grandchild, within: 5), "process group: grandchild is terminated too")
    } catch {
        check(false, "process group terminate (\(error))")
    }
}

func checkProcessGroupExitCode() {
    let dir = tempDir()
    do {
        let pid = try ProcessGroup.spawn("/bin/zsh", arguments: ["-c", "echo $WORKLOG_TRIGGER; exit 3"], environment: ["WORKLOG_TRIGGER": "manual"],
                                         outputPath: dir.appendingPathComponent("out.log").path)
        check(ProcessGroup.wait(pid) == 3, "process group: exit code is returned")
        check((try? String(contentsOf: dir.appendingPathComponent("out.log"), encoding: .utf8)) == "manual\n", "process group: env and output reach the child")
    } catch {
        check(false, "process group exit code (\(error))")
    }
}
