import Foundation
import WorkLogCore

// Derived from #filePath so the checks do not depend on the current directory.
let repoRoot = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent().deletingLastPathComponent()
    .deletingLastPathComponent().deletingLastPathComponent()

func calendar(_ zone: String = "Asia/Seoul") -> Calendar {
    var cal = Calendar(identifier: .gregorian)
    cal.timeZone = TimeZone(identifier: zone)!
    return cal
}

func date(_ cal: Calendar, _ y: Int, _ mo: Int, _ d: Int, _ h: Int, _ mi: Int) -> Date {
    cal.date(from: DateComponents(year: y, month: mo, day: d, hour: h, minute: mi))!
}

func schedule(
    mode: AppSettings.Schedule.Mode = .times,
    times: [String] = [],
    hours: Int = 4,
    anchor: String = "08:00",
    quiet: [(String, String)] = []
) -> AppSettings.Schedule {
    AppSettings.Schedule(
        mode: mode,
        times: times.map { ClockTime(string: $0)! },
        interval: .init(hours: hours, anchor: ClockTime(string: anchor)!),
        quietRanges: quiet.map { .init(start: ClockTime(string: $0.0)!, end: ClockTime(string: $0.1)!) }
    )
}

func checkTimesNextSameDay() {
    let cal = calendar()
    let s = schedule(times: ["10:00", "22:00"])
    let next = ScheduleCalculator.nextRun(s, after: date(cal, 2026, 10, 29, 14, 46), calendar: cal)
    check(next == date(cal, 2026, 10, 29, 22, 0), "times: next slot is the same day")
}

func checkTimesWrapsToTomorrow() {
    let cal = calendar()
    let s = schedule(times: ["10:00", "22:00"])
    let next = ScheduleCalculator.nextRun(s, after: date(cal, 2026, 10, 29, 22, 30), calendar: cal)
    check(next == date(cal, 2026, 10, 30, 10, 0), "times: wraps to tomorrow")
}

func checkIntervalRestartsDaily() {
    let cal = calendar()
    let s = schedule(mode: .interval, hours: 5, anchor: "08:00")
    let late = ScheduleCalculator.nextRun(s, after: date(cal, 2026, 10, 29, 23, 30), calendar: cal)
    check(late == date(cal, 2026, 10, 30, 4, 0), "interval: 23:30 gives 04:00 next day")
    let early = ScheduleCalculator.nextRun(s, after: date(cal, 2026, 10, 29, 4, 30), calendar: cal)
    check(early == date(cal, 2026, 10, 29, 8, 0), "interval: 04:30 gives 08:00")
}

func checkIntervalYesterdaysCycleReachesThisMorning() {
    let cal = calendar()
    let s = schedule(mode: .interval, hours: 5, anchor: "08:00")
    let next = ScheduleCalculator.nextRun(s, after: date(cal, 2026, 10, 29, 1, 0), calendar: cal)
    check(next == date(cal, 2026, 10, 29, 4, 0), "interval: 01:00 gives 04:00 from yesterday's cycle")
}

func checkIntervalFourHoursCoversNight() {
    let cal = calendar()
    let s = schedule(mode: .interval, hours: 4, anchor: "08:00")
    let next = ScheduleCalculator.nextRun(s, after: date(cal, 2026, 10, 29, 20, 30), calendar: cal)
    check(next == date(cal, 2026, 10, 30, 0, 0), "interval: 4 h from 08:00 covers the night")
}

func checkQuietStartInclusiveEndExclusive() {
    let cal = calendar()
    let s = schedule(mode: .interval, hours: 4, anchor: "08:00", quiet: [("00:00", "08:00")])
    let next = ScheduleCalculator.nextRun(s, after: date(cal, 2026, 10, 29, 20, 30), calendar: cal)
    check(next == date(cal, 2026, 10, 30, 8, 0), "quiet: start inclusive, end exclusive")
}

func checkQuietCrossesMidnight() {
    let cal = calendar()
    let s = schedule(times: ["23:30", "06:00", "09:00"], quiet: [("23:00", "07:00")])
    let next = ScheduleCalculator.nextRun(s, after: date(cal, 2026, 10, 29, 22, 0), calendar: cal)
    check(next == date(cal, 2026, 10, 30, 9, 0), "quiet: range crossing midnight")
}

func checkNoSlotIn48hReturnsNil() {
    let cal = calendar()
    let s = schedule(times: ["01:00"], quiet: [("00:00", "02:00")])
    let next = ScheduleCalculator.nextRun(s, after: date(cal, 2026, 10, 29, 12, 0), calendar: cal)
    check(next == nil, "no slot within 48h returns nil")
}

func checkDSTSpringForwardSkipsMissingSlot() {
    let cal = calendar("America/New_York")
    let s = schedule(times: ["02:30"])
    let next = ScheduleCalculator.nextRun(s, after: date(cal, 2027, 3, 14, 0, 0), calendar: cal)
    check(next == date(cal, 2027, 3, 15, 2, 30), "DST spring forward skips the missing 02:30")
}

func checkMissedGrace() {
    let slot = Date(timeIntervalSince1970: 1_000_000)
    check(!ScheduleCalculator.isMissed(slot: slot, firedAt: slot.addingTimeInterval(119)), "119 s late is not missed")
    check(ScheduleCalculator.isMissed(slot: slot, firedAt: slot.addingTimeInterval(121)), "121 s late is missed")
}

func checkSettingsFixtureRoundTrip() {
    do {
        let data = try Data(contentsOf: repoRoot.appendingPathComponent("fixtures/settings.json"))
        let decoded = try JSONDecoder().decode(AppSettings.self, from: data)
        let again = try JSONDecoder().decode(AppSettings.self, from: JSONEncoder().encode(decoded))
        check(decoded == again, "fixture round-trips")
        check(decoded.schedule.interval.hours == 6, "fixture interval hours")
        check(decoded.schedule.mode == .interval && decoded.slack?.userId == "UFIXTURE1", "fixture mode and slack block")
    } catch {
        check(false, "fixture round-trips (\(error))")
    }
}

func checkIntervalHoursOutOfRangeThrows() {
    for hours in [0, -3, 25] {
        let json = Data("{\"schedule\":{\"interval\":{\"hours\":\(hours)}}}".utf8)
        check((try? JSONDecoder().decode(AppSettings.self, from: json)) == nil, "interval hours \(hours) fails to decode")
    }
    let edge = Data("{\"schedule\":{\"interval\":{\"hours\":24}}}".utf8)
    check((try? JSONDecoder().decode(AppSettings.self, from: edge)) != nil, "interval hours 24 decodes")
}

func checkMissingKeysUseDefaults() {
    let decoded = try? JSONDecoder().decode(AppSettings.self, from: Data("{}".utf8))
    check(decoded == AppSettings.defaults, "empty object decodes to defaults")
    check(decoded?.notifyOnSuccess == true, "notifyOnSuccess defaults to true")
    check(AppSettings.defaults.logFolder == "~/WorkLog", "logFolder defaults to ~/WorkLog")
    let collectorOnly = Data("{\"slack\": {\"userId\": \"U1\", \"displayName\": \"Name\"}}".utf8)
    check((try? JSONDecoder().decode(AppSettings.self, from: collectorOnly))?.scheduleEnabled == false,
          "a file the app never saved (slack block only) keeps the schedule off")
    let appSaved = Data("{\"version\": 1}".utf8)
    check((try? JSONDecoder().decode(AppSettings.self, from: appSaved))?.scheduleEnabled == true,
          "a file the app saved before the key existed keeps the schedule on")
}

func checkScheduleEnabledDecoding() {
    let dir = tempDir()
    let url = dir.appendingPathComponent("settings.json")
    check((try? SettingsStore.load(url))?.scheduleEnabled == false, "schedule: a fresh install starts with the schedule off")
    writeJSON("{\"version\": 1, \"provider\": \"claude\"}", to: url)
    check((try? SettingsStore.load(url))?.scheduleEnabled == true, "schedule: an existing file without the key keeps running")
    writeJSON("{\"scheduleEnabled\": false}", to: url)
    check((try? SettingsStore.load(url))?.scheduleEnabled == false, "schedule: an explicit false is kept")
    var settings = AppSettings.defaults
    settings.scheduleEnabled = true
    try? SettingsStore.save(settings, to: url)
    let raw = (try? JSONSerialization.jsonObject(with: Data(contentsOf: url))) as? [String: Any]
    check(raw?["scheduleEnabled"] as? Bool == true, "schedule: the app writes scheduleEnabled")
}

func checkNoSlotWhileScheduleDisabled() {
    let cal = calendar()
    var settings = AppSettings.defaults
    settings.schedule = schedule(times: ["10:00", "22:00"])
    let now = date(cal, 2026, 10, 29, 14, 46)
    settings.scheduleEnabled = false
    check(ScheduleCalculator.nextRun(settings, after: now, calendar: cal) == nil, "schedule: no slot while disabled")
    settings.scheduleEnabled = true
    check(ScheduleCalculator.nextRun(settings, after: now, calendar: cal) == date(cal, 2026, 10, 29, 22, 0),
          "schedule: enabled gives the next slot")
}

func tempDir() -> URL {
    let url = FileManager.default.temporaryDirectory.appendingPathComponent("worklog-checks-\(UUID().uuidString)")
    try! FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    return url
}

func rawRecords(_ url: URL) -> [[String: Any]] {
    let data = try! Data(contentsOf: url)
    let root = try! JSONSerialization.jsonObject(with: data) as! [String: Any]
    return root["suggestions"] as! [[String: Any]]
}

func sameJSON(_ a: Any?, _ b: Any?) -> Bool {
    guard let a, let b else { return a == nil && b == nil }
    return (a as AnyObject).isEqual(b as AnyObject)
}

// Copies the fixture and optionally adds an unknown key to every record.
func suggestionsCopy(extraKey: Bool = false) -> URL {
    let dir = tempDir()
    let dest = dir.appendingPathComponent("suggestions.json")
    let data = try! Data(contentsOf: repoRoot.appendingPathComponent("fixtures/suggestions.json"))
    var root = try! JSONSerialization.jsonObject(with: data) as! [String: Any]
    if extraKey {
        root["suggestions"] = (root["suggestions"] as! [[String: Any]]).map { var r = $0; r["x"] = 1; return r }
    }
    try! JSONSerialization.data(withJSONObject: root).write(to: dest)
    return dest
}

func checkSuggestionLoadFixture() {
    let list = try? SuggestionStore.load(repoRoot.appendingPathComponent("fixtures/suggestions.json"))
    check(list?.count == 3, "suggestions: fixture loads three records")
    check(list?.first?.isPending == true && list?[1].pendingAnswer?.answer == "accept", "suggestions: status and pendingAnswer decode")
}

func checkAnswerKeepsUnknownKeys() {
    let url = suggestionsCopy(extraKey: true)
    let now = Date(timeIntervalSince1970: 1_793_000_000)
    try? SuggestionStore.answer(url, id: "fx-pending-1", answer: .accept, description: "Edited", now: now)
    let records = rawRecords(url)
    let target = records.first { $0["id"] as? String == "fx-pending-1" }
    check(target?["x"] as? Int == 1, "answer keeps unknown key x")
    check(target?["status"] as? String == "answered", "answer sets status answered")
    let pending = target?["pendingAnswer"] as? [String: Any]
    check(pending?["answer"] as? String == "accept" && pending?["description"] as? String == "Edited", "answer writes pendingAnswer")
    check(ISODate.parse(pending?["answeredAt"] as? String ?? "") == now, "answeredAt is a parsable ISO-8601 timestamp")
    check(records.count == 3 && records.allSatisfy { $0["x"] as? Int == 1 }, "answer keeps other records and their unknown keys")
}

func checkAnswerNeverSetsFlag() {
    let url = suggestionsCopy()
    try? SuggestionStore.answer(url, id: "fx-pending-1", answer: .never, description: nil, now: Date())
    let target = rawRecords(url).first { $0["id"] as? String == "fx-pending-1" }
    check(target?["neverSuggest"] as? Bool == true, "never sets neverSuggest")
    check((target?["pendingAnswer"] as? [String: Any])?["answer"] as? String == "reject", "never writes answer reject")
    let rejected = suggestionsCopy()
    try? SuggestionStore.answer(rejected, id: "fx-pending-1", answer: .reject, description: nil, now: Date())
    let other = rawRecords(rejected).first { $0["id"] as? String == "fx-pending-1" }
    check(other?["neverSuggest"] as? Bool == false, "reject leaves neverSuggest false")
}

func checkAnswerRequiresPending() {
    let url = suggestionsCopy()
    for id in ["fx-answered-1", "fx-rejected-1"] {
        let before = rawRecords(url).first { $0["id"] as? String == id }
        var thrown = false
        do { try SuggestionStore.answer(url, id: id, answer: .accept, description: nil, now: Date()) } catch { thrown = true }
        let after = rawRecords(url).first { $0["id"] as? String == id }
        check(thrown && sameJSON(before, after), "answer on non-pending \(id) throws and changes nothing")
    }
    var missing = false
    do { try SuggestionStore.answer(url, id: "nope", answer: .accept, description: nil, now: Date()) } catch { missing = true }
    check(missing, "answer on unknown id throws")
}

func checkSetNeverSuggestOnly() {
    let url = suggestionsCopy(extraKey: true)
    let before = rawRecords(url)
    try? SuggestionStore.setNeverSuggest(url, id: "fx-answered-1", true)
    let after = rawRecords(url)
    var changed: [String] = []
    for (b, a) in zip(before, after) {
        for key in Set(b.keys).union(a.keys) where !sameJSON(b[key], a[key]) {
            changed.append("\(b["id"] as! String).\(key)")
        }
    }
    check(changed == ["fx-answered-1.neverSuggest"], "setNeverSuggest changes only that field (changed: \(changed))")
    check(after[1]["neverSuggest"] as? Bool == true, "setNeverSuggest writes the value")
}

func checkLockTimeout() {
    let dir = tempDir()
    let lockURL = dir.appendingPathComponent("x.lock")
    let fd = open(lockURL.path, O_CREAT | O_RDWR, 0o644)
    check(flock(fd, LOCK_EX | LOCK_NB) == 0, "test holds the lock")
    var thrown = false
    let started = Date()
    do { try FileLock.withLock(at: lockURL, timeout: 0.2) {} } catch { thrown = true }
    check(thrown && Date().timeIntervalSince(started) < 2, "withLock throws after the timeout")
    flock(fd, LOCK_UN)
    close(fd)
    let value = try? FileLock.withLock(at: lockURL, timeout: 0.2) { 42 }
    check(value == 42, "withLock runs once the lock is free")
}

func runsCopyWithGarbage() -> URL {
    let url = tempDir().appendingPathComponent("runs.jsonl")
    var text = try! String(contentsOf: repoRoot.appendingPathComponent("fixtures/runs.jsonl"), encoding: .utf8)
    if !text.hasSuffix("\n") { text += "\n" }
    try! (text + "not json at all\n{\"startedAt\": 1}\n").write(to: url, atomically: true, encoding: .utf8)
    return url
}

func checkRunLogSkipsBadLines() {
    let runs = RunLog.load(runsCopyWithGarbage())
    check(runs.count == 4, "runs: bad lines are skipped (got \(runs.count))")
    check(runs.first?.costUsd == 0.97 && runs[1].tokens == 55463 && runs[2].reason == "Provider not found"
          && runs.first?.summary == "Wrote 2 days to the monthly log." && runs[2].summary == nil, "runs: fields decode")
    check(RunLog.load(tempDir().appendingPathComponent("missing.jsonl")).isEmpty, "runs: missing file is empty")
}

func checkMonthTotals() {
    let runs = RunLog.load(repoRoot.appendingPathComponent("fixtures/runs.jsonl"))
    let october = DateComponents(year: 2026, month: 10)
    let totals = RunLog.monthTotals(runs, month: october, provider: .claude, calendar: calendar())
    check(totals.runs == 2 && abs(totals.costUsd - 0.97) < 1e-9 && totals.tokens == 55463,
          "monthTotals: only runs where the provider ran are counted (got \(totals.runs))")
    check(totals.runsWithoutCost == 0, "monthTotals: Codex runs never have a cost, so the Claude view does not count them")
    let start = runs[0].startedAt
    let uncosted = RunRecord(startedAt: start, endedAt: start, trigger: .manual, provider: .claude, result: .failed,
                             reason: "Provider reported an error", logPath: "/tmp/x.json")
    let withUncosted = RunLog.monthTotals(runs + [uncosted], month: october, provider: .claude, calendar: calendar())
    check(withUncosted.runsWithoutCost == 1, "monthTotals: a Claude run without cost data is counted apart")
    let stopped = RunRecord.appFailure(trigger: .manual, provider: .claude, startedAt: start, endedAt: start,
                                       reason: RunRecord.stoppedOnQuitReason)
    check(RunLog.monthTotals(runs + [stopped], month: october, provider: .claude, calendar: calendar()).runs == 2,
          "monthTotals: app-recorded failures are not provider runs")
    let other = RunLog.monthTotals(runs, month: DateComponents(year: 2026, month: 11), provider: .claude, calendar: calendar())
    check(other.runs == 0 && other.costUsd == 0 && other.tokens == 0 && other.runsWithoutCost == 0, "monthTotals: other month is empty")
    check(DisplayText.monthSummary(withUncosted, showsTokens: false, strings: .en) == "This month: 3 runs, $0.97 (+1 without cost data)",
          "monthTotals: $ view names runs without cost data")
    check(DisplayText.monthSummary(totals, showsTokens: false, strings: .en) == "This month: 2 runs, $0.97",
          "monthTotals: $ view has no suffix for Codex runs")
    check(DisplayText.monthSummary(totals, showsTokens: true, strings: .en) == "This month: 2 runs, 55,463 tokens", "monthTotals: tokens view")
    check(DisplayText.monthSummary(withUncosted, showsTokens: false, strings: .ko) == "이번 달: 3회 실행, $0.97 (비용 정보 없는 실행 +1회)",
          "monthTotals: ko $ view names runs without cost data")
    check(DisplayText.monthSummary(totals, showsTokens: false, strings: .ko) == "이번 달: 2회 실행, $0.97", "monthTotals: ko $ view")
    check(DisplayText.monthSummary(totals, showsTokens: true, strings: .ko) == "이번 달: 2회 실행, 55,463 토큰", "monthTotals: ko tokens view")
}

func checkSuggestionLoadSkipsBrokenRecords() {
    let url = tempDir().appendingPathComponent("suggestions.json")
    let data = try! Data(contentsOf: repoRoot.appendingPathComponent("fixtures/suggestions.json"))
    var root = try! JSONSerialization.jsonObject(with: data) as! [String: Any]
    var records = root["suggestions"] as! [[String: Any]]
    records[1]["status"] = "weird"
    records[2].removeValue(forKey: "name")
    root["suggestions"] = records + [["id": 7]]
    try! JSONSerialization.data(withJSONObject: root).write(to: url)
    let loaded = try? SuggestionStore.load(url)
    check(loaded?.map(\.id) == ["fx-pending-1"], "suggestions: broken records are skipped, the rest load")
    writeJSON("{not json", to: url)
    check((try? SuggestionStore.load(url)) == nil, "suggestions: a broken file still throws")
}

func mode(_ url: URL) -> Int? {
    (try? FileManager.default.attributesOfItem(atPath: url.path)[.posixPermissions] as? Int) ?? nil
}

func checkDataFilesAreOwnerOnly() {
    let dir = tempDir()
    let settings = dir.appendingPathComponent("settings.json")
    try? SettingsStore.save(.defaults, to: settings)
    check(mode(settings) == 0o600, "private: settings.json is 0600")
    let suggestions = suggestionsCopy()
    try? SuggestionStore.setNeverSuggest(suggestions, id: "fx-pending-1", true)
    check(mode(suggestions) == 0o600, "private: suggestions.json is 0600")
    check(mode(suggestions.deletingLastPathComponent().appendingPathComponent("suggestions.json.lock")) == 0o600,
          "private: lock file is 0600")
    let runs = dir.appendingPathComponent("runs.jsonl")
    try? RunLog.append(runs, runRecord(.skipped, at: 0, reason: "Slot passed"))
    check(mode(runs) == 0o600, "private: runs.jsonl is 0600")
}

func checkRunLogAppend() {
    let url = tempDir().appendingPathComponent("runs.jsonl")
    let start = Date(timeIntervalSince1970: 1_793_000_000)
    let skipped = RunRecord(startedAt: start, endedAt: start, trigger: .schedule, provider: .claude, result: .skipped, reason: "Slot passed")
    try? RunLog.append(url, skipped)
    try? RunLog.append(url, skipped)
    let text = (try? String(contentsOf: url, encoding: .utf8)) ?? ""
    let lines = text.split(separator: "\n")
    check(text.hasSuffix("\n") && lines.count == 2, "append: one line per record, file created")
    let obj = lines.first.flatMap { try? JSONSerialization.jsonObject(with: Data($0.utf8)) as? [String: Any] }
    check(Set(obj?.keys.map { $0 } ?? []) == ["startedAt", "endedAt", "trigger", "provider", "result", "reason", "costUsd", "tokens", "summary", "logPath"],
          "append: all ten keys are written, nulls included")
    check(RunLog.load(url) == [skipped, skipped], "append: lines load back equal")
}

func writeJSON(_ text: String, to url: URL) {
    try! text.write(to: url, atomically: true, encoding: .utf8)
}

func checkClaudeUsageParse() {
    let url = tempDir().appendingPathComponent("claude-rate-limits.json")
    writeJSON("""
    {"five_hour": {"used_percentage": 5.0, "resets_at": 1793270000}, "seven_day": null, "updatedAt": "2026-10-29T10:00:00+09:00"}
    """, to: url)
    let usage = Usage.claude(url)
    check(usage?.fiveHour == UsageWindow(usedPercent: 5.0, resetsAt: Date(timeIntervalSince1970: 1_793_270_000)), "claude usage: five_hour parses")
    check(usage?.weekly == nil && usage?.updatedAt == ISODate.parse("2026-10-29T10:00:00+09:00"), "claude usage: null window and updatedAt")
    check(Usage.claude(tempDir().appendingPathComponent("none.json")) == nil, "claude usage: missing file is nil")
    writeJSON("garbage", to: url)
    check(Usage.claude(url) == nil, "claude usage: garbage is nil")
}

func codexLine(_ used: Double, ts: String = "2026-10-29T01:00:00.000Z") -> String {
    """
    {"timestamp": "\(ts)", "type": "event_msg", "payload": {"type": "token_count", "rate_limits": {"primary": {"used_percent": \(used), "window_minutes": 300, "resets_at": 1793270000}, "secondary": {"used_percent": 30.0, "window_minutes": 10080, "resets_at": 1793600000}}}}
    """
}

func codexSession(_ root: URL, _ name: String, lines: [String], modified: Date) {
    let dir = root.appendingPathComponent("2026/10/29")
    try! FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
    let file = dir.appendingPathComponent(name)
    writeJSON(lines.joined(separator: "\n") + "\n", to: file)
    try! FileManager.default.setAttributes([.modificationDate: modified], ofItemAtPath: file.path)
}

func checkCodexUsageNewestFile() {
    let root = tempDir()
    let now = Date()
    // The older file has the later name, so a name-based pick would choose it.
    codexSession(root, "z-old.jsonl", lines: [codexLine(90)], modified: now.addingTimeInterval(-600))
    codexSession(root, "a-new.jsonl", lines: [codexLine(10), "{\"type\": \"other\"}", codexLine(12.5)], modified: now)
    let usage = Usage.codex(sessionsRoot: root)
    check(usage?.fiveHour?.usedPercent == 12.5, "codex usage: newest file, last rate_limits line wins")
    check(usage?.weekly == UsageWindow(usedPercent: 30.0, resetsAt: Date(timeIntervalSince1970: 1_793_600_000)), "codex usage: secondary maps to weekly")
    check(usage?.updatedAt == ISODate.parse("2026-10-29T01:00:00.000Z"), "codex usage: updatedAt is the line timestamp")
}

func checkCodexUsageLenientKeys() {
    let root = tempDir()
    codexSession(root, "s.jsonl", lines: ["""
    {"timestamp": "2026-10-29T01:00:00Z", "payload": {"rate_limits": {"primary": {"used_percentage": 7, "resets_in_seconds": 600}}}}
    """], modified: Date())
    let usage = Usage.codex(sessionsRoot: root)
    let base = ISODate.parse("2026-10-29T01:00:00Z")!
    check(usage?.fiveHour == UsageWindow(usedPercent: 7, resetsAt: base.addingTimeInterval(600)), "codex usage: used_percentage and resets_in_seconds")
    check(usage?.weekly == nil, "codex usage: missing secondary is nil")
}

func checkCodexUsageGarbageIsNil() {
    let root = tempDir()
    check(Usage.codex(sessionsRoot: root) == nil, "codex usage: no sessions is nil")
    codexSession(root, "s.jsonl", lines: ["{\"rate_limits\": \"nope\"", "plain text rate_limits"], modified: Date())
    check(Usage.codex(sessionsRoot: root) == nil, "codex usage: garbage is nil")
}

checkTimesNextSameDay()
checkTimesWrapsToTomorrow()
checkIntervalRestartsDaily()
checkIntervalFourHoursCoversNight()
checkIntervalYesterdaysCycleReachesThisMorning()
checkQuietStartInclusiveEndExclusive()
checkQuietCrossesMidnight()
checkNoSlotIn48hReturnsNil()
checkDSTSpringForwardSkipsMissingSlot()
checkMissedGrace()
checkSettingsFixtureRoundTrip()
checkIntervalHoursOutOfRangeThrows()
checkMissingKeysUseDefaults()
checkScheduleEnabledDecoding()
checkNoSlotWhileScheduleDisabled()

checkSuggestionLoadFixture()
checkSuggestionLoadSkipsBrokenRecords()
checkDataFilesAreOwnerOnly()
checkAnswerKeepsUnknownKeys()
checkAnswerNeverSetsFlag()
checkAnswerRequiresPending()
checkSetNeverSuggestOnly()
checkLockTimeout()
checkRunLogSkipsBadLines()
checkMonthTotals()
checkRunLogAppend()
checkClaudeUsageParse()
checkCodexUsageNewestFile()
checkCodexUsageLenientKeys()
checkCodexUsageGarbageIsNil()

checkSettingsSaveKeepsForeignKeys()
checkSettingsLoadMissingAndBroken()
checkAppLanguageSetting()
checkBrokenFileBackUp()
checkSlotDecision()
checkLastRunIgnoresSkipped()
checkRunRecordForSpawn()
checkNewPendingCount()
checkNotificationText()
checkWarningsMark()
checkAppFailureRecord()
checkDisplayText()
checkKoreanDisplayText()
checkProcessGroupTerminate()
checkProcessGroupExitCode()

print("\(passedCount) passed, \(failedCount) failed")
exit(failedCount > 0 ? 1 : 0)
