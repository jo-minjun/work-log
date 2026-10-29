import AppKit
import SwiftUI
import WorkLogCore

@MainActor
final class AppModel: ObservableObject {
    enum UsageState {
        case loaded(UsageSnapshot)
        case noData
        case unavailable
    }

    enum DataFile {
        case settings, suggestions
    }

    // Kept as data and turned into text on display, so a banner follows a language switch.
    enum ActionError {
        case backUp(file: String, detail: String)
        case saveSettings(detail: String)
        case saveAnswer(detail: String)

        func message(_ strings: UIStrings) -> String {
            switch self {
            case .backUp(let file, let detail): strings.couldNotBackUp(file, detail)
            case .saveSettings(let detail): strings.couldNotSaveSettings(detail)
            case .saveAnswer(let detail): strings.couldNotSaveAnswer(detail)
            }
        }
    }

    // The store already waits 10 s per attempt; spec §11 asks the app to retry a save that timed out.
    private static let lockAttempts = 3
    private static let refreshInterval: TimeInterval = 60

    @Published private(set) var settings: AppSettings = .defaults
    @Published private(set) var settingsError: String?
    @Published private(set) var suggestions: [Suggestion] = []
    @Published private(set) var suggestionsError: String?
    @Published private(set) var runs: [RunRecord] = []
    @Published private(set) var usage: UsageState = .noData
    @Published private(set) var nextRun: Date?
    @Published private(set) var isRunning = false
    @Published private(set) var answering: Set<String> = []
    @Published private(set) var now = Date()
    @Published var actionError: ActionError?

    let paths: AppPaths
    private let runner: Runner
    private let notifier = Notifier()
    private var watcher: FileWatcher?
    private var slotTimer: Timer?
    private var scheduledSlot: Date?
    private var knownPending: Set<String>?

    init(paths: AppPaths = .current()) {
        self.paths = paths
        runner = Runner(paths: paths)
        runner.onFinish = { [weak self] in self?.runFinished($0) }
    }

    // MARK: Derived state

    var pendingSuggestions: [Suggestion] { suggestions.filter(\.isPending) }
    var pastSuggestions: [Suggestion] { suggestions.filter { !$0.isPending } }
    var lastRun: RunRecord? { RunOutcome.lastRun(runs) }
    var lastRunMark: RunMark { RunOutcome.lastRunMark(runs) }

    var monthTotals: MonthTotals {
        RunLog.monthTotals(runs, month: Calendar.current.dateComponents([.year, .month], from: now), provider: settings.provider)
    }

    var strings: UIStrings { .for(settings.appLanguage) }

    var settingsErrorMessage: String? { settingsError.map(strings.settingsUnreadable) }
    var suggestionsErrorMessage: String? { suggestionsError.map(strings.suggestionsUnreadable) }
    var actionErrorMessage: String? { actionError?.message(strings) }

    var slackStatus: String {
        guard let slack = settings.slack, let userId = slack.userId else { return strings.slackNotChecked }
        let who = "\(slack.displayName ?? userId) (\(userId))"
        guard let checked = slack.checkedAt.flatMap(ISODate.parse) else { return who }
        let formatter = RelativeDateTimeFormatter()
        formatter.locale = strings.locale
        return strings.slackChecked(who, formatter.localizedString(for: checked, relativeTo: now))
    }

    // MARK: Lifecycle

    func start() {
        try? FileManager.default.createDirectory(at: paths.dataDir, withIntermediateDirectories: true,
                                                 attributes: [.posixPermissions: AppPaths.privateDirectoryMode])
        notifier.requestAuthorization()
        reloadAll()
        if settingsError == nil { LoginItem.applyOnFirstLaunch(settings.launchAtLogin) }

        let watcher = FileWatcher(directory: paths.dataDir, names: [
            paths.settings.lastPathComponent, paths.suggestions.lastPathComponent,
            paths.runs.lastPathComponent, paths.claudeRateLimits.lastPathComponent,
        ]) { [weak self] in self?.reload($0) }
        watcher.start()
        self.watcher = watcher

        observe(NSWorkspace.shared.notificationCenter, NSWorkspace.didWakeNotification) { $0.recomputeSchedule(); $0.reloadUsage() }
        observe(.default, .NSSystemClockDidChange) { $0.recomputeSchedule() }
        observe(.default, .NSSystemTimeZoneDidChange) {
            NSTimeZone.resetSystemTimeZone()
            $0.recomputeSchedule()
        }
        let timer = Timer(timeInterval: Self.refreshInterval, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                self?.now = Date()
                self?.reloadUsage()
            }
        }
        RunLoop.main.add(timer, forMode: .common)
        recomputeSchedule()
    }

    // Covers logout and any quit path that skipped the confirmation. A killed run.sh writes no line, so the app does.
    func stopRunForQuit() {
        guard let stopped = runner.terminate() else { return }
        appendRun(.appFailure(trigger: stopped.trigger, provider: stopped.provider, startedAt: stopped.spawnedAt,
                              endedAt: Date(), reason: RunRecord.stoppedOnQuitReason))
    }

    func quit() {
        if runner.isRunning {
            NSApp.activate(ignoringOtherApps: true)
            let alert = NSAlert()
            alert.messageText = strings.quitAlertTitle
            alert.informativeText = strings.quitAlertBody
            alert.addButton(withTitle: strings.quit)
            alert.addButton(withTitle: strings.cancel)
            guard alert.runModal() == .alertFirstButtonReturn else { return }
            stopRunForQuit()
        }
        NSApp.terminate(nil)
    }

    // The model lives as long as the app, so the observer tokens are never needed for removal.
    private func observe(_ center: NotificationCenter, _ name: Notification.Name, _ handler: @escaping (AppModel) -> Void) {
        _ = center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self else { return }
                handler(self)
            }
        }
    }

    // MARK: Loading

    func reloadAll() {
        now = Date()
        reloadSettings()
        reloadSuggestions()
        reloadRuns()
        reloadUsage()
    }

    private func reload(_ changed: Set<String>) {
        now = Date()
        let provider = settings.provider
        if changed.contains(paths.settings.lastPathComponent) { reloadSettings() }
        if changed.contains(paths.suggestions.lastPathComponent) { reloadSuggestions() }
        if changed.contains(paths.runs.lastPathComponent) { reloadRuns() }
        if changed.contains(paths.claudeRateLimits.lastPathComponent) || provider != settings.provider { reloadUsage() }
    }

    private func reloadRuns() {
        let loaded = RunLog.load(paths.runs)
        if loaded != runs { runs = loaded }
    }

    private func reloadSettings() {
        let before = (settings.schedule, settings.scheduleEnabled, settingsError == nil)
        do {
            settings = try SettingsStore.load(paths.settings)
            settingsError = nil
        } catch {
            settingsError = Self.describe(error)
        }
        if before != (settings.schedule, settings.scheduleEnabled, settingsError == nil) { recomputeSchedule() }
    }

    private func reloadSuggestions() {
        do {
            suggestions = try SuggestionStore.load(paths.suggestions)
            suggestionsError = nil
        } catch {
            suggestionsError = Self.describe(error)
            return
        }
        let pending = Set(pendingSuggestions.map(\.id))
        let added = RunOutcome.newPendingCount(previous: knownPending, current: pending)
        knownPending = pending
        if added > 0 { notifier.post(.newSuggestions(added, strings: strings)) }
    }

    // Walking ~/.codex/sessions can take a while, so usage is read off the main thread.
    func reloadUsage() {
        let provider = settings.provider, paths = paths
        DispatchQueue.global(qos: .utility).async { [weak self] in
            let state: UsageState
            switch provider {
            case .claude:
                let exists = FileManager.default.fileExists(atPath: paths.claudeRateLimits.path)
                state = exists ? Usage.claude(paths.claudeRateLimits).map(UsageState.loaded) ?? .unavailable : .noData
            case .codex:
                let exists = FileManager.default.fileExists(atPath: paths.codexSessions.path)
                state = exists ? Usage.codex(sessionsRoot: paths.codexSessions).map(UsageState.loaded) ?? .unavailable : .noData
            }
            DispatchQueue.main.async { [weak self] in
                MainActor.assumeIsolated {
                    guard let self, self.settings.provider == provider else { return }
                    self.usage = state
                }
            }
        }
    }

    func backUpAndReset(_ file: DataFile) {
        let url = file == .settings ? paths.settings : paths.suggestions
        do {
            try BrokenFile.backUp(url, now: Date())
        } catch {
            actionError = .backUp(file: url.lastPathComponent, detail: Self.describe(error))
        }
        reloadAll()
    }

    // MARK: Settings

    func binding<T: Equatable>(_ keyPath: WritableKeyPath<AppSettings, T>) -> Binding<T> {
        Binding(get: { self.settings[keyPath: keyPath] }, set: { value in self.updateSettings { $0[keyPath: keyPath] = value } })
    }

    func updateSettings(_ change: (inout AppSettings) -> Void) {
        guard settingsError == nil else { return }
        var next = settings
        change(&next)
        guard next != settings else { return }
        do {
            try SettingsStore.save(next, to: paths.settings)
        } catch {
            actionError = .saveSettings(detail: Self.describe(error))
            return
        }
        let loginChanged = next.launchAtLogin != settings.launchAtLogin
        let providerChanged = next.provider != settings.provider
        settings = next
        if loginChanged { LoginItem.apply(next.launchAtLogin) }
        if providerChanged { reloadUsage() }
        recomputeSchedule()
    }

    func addTime(_ time: ClockTime) {
        updateSettings { s in
            guard !s.schedule.times.contains(time) else { return }
            s.schedule.times.append(time)
            s.schedule.times.sort { $0.minutesOfDay < $1.minutesOfDay }
        }
    }

    func removeTime(_ time: ClockTime) {
        updateSettings { $0.schedule.times.removeAll { $0 == time } }
    }

    func addQuietRange(_ range: AppSettings.Schedule.QuietRange) {
        guard range.start != range.end else { return }
        updateSettings { s in
            guard !s.schedule.quietRanges.contains(range) else { return }
            s.schedule.quietRanges.append(range)
        }
    }

    func removeQuietRange(at index: Int) {
        updateSettings { s in
            guard s.schedule.quietRanges.indices.contains(index) else { return }
            s.schedule.quietRanges.remove(at: index)
        }
    }

    func addSessionFolders(_ folders: [String]) {
        updateSettings { s in
            for folder in folders where !s.sessionFolders.contains(folder) { s.sessionFolders.append(folder) }
        }
    }

    func removeSessionFolder(_ folder: String) {
        updateSettings { $0.sessionFolders.removeAll { $0 == folder } }
    }

    // MARK: Schedule

    // A sleep pauses the timer without firing it, so any slot already behind us is handled here as a late fire.
    private func recomputeSchedule() {
        slotTimer?.invalidate()
        slotTimer = nil
        let current = Date()
        if let slot = scheduledSlot, slot <= current {
            scheduledSlot = nil
            handleSlot(slot, firedAt: current)
        }
        guard settingsError == nil,
              let next = ScheduleCalculator.nextRun(settings, after: current, calendar: .current) else {
            scheduledSlot = nil
            nextRun = nil
            return
        }
        scheduledSlot = next
        nextRun = next
        let timer = Timer(fire: next, interval: 0, repeats: false) { [weak self] _ in
            MainActor.assumeIsolated { self?.recomputeSchedule() }
        }
        RunLoop.main.add(timer, forMode: .common)
        slotTimer = timer
    }

    private func handleSlot(_ slot: Date, firedAt: Date) {
        switch SlotDecision.decide(slot: slot, firedAt: firedAt, isRunning: runner.isRunning) {
        case .run:
            startRun(.schedule)
        case .skip(let reason):
            appendRun(RunRecord(startedAt: slot, endedAt: firedAt, trigger: .schedule, provider: settings.provider,
                                result: .skipped, reason: reason))
            reloadRuns()
        }
    }

    private func appendRun(_ record: RunRecord) {
        do {
            try RunLog.append(paths.runs, record)
        } catch {
            AppEnvironment.log("could not record a \(record.result.rawValue) run: \(error)")
        }
    }

    // MARK: Runs

    func runNow() {
        startRun(.manual)
    }

    private func startRun(_ trigger: RunRecord.Trigger) {
        guard !runner.isRunning else { return }
        do {
            try runner.start(trigger: trigger, provider: settings.provider)
            isRunning = true
        } catch {
            AppEnvironment.log("run did not start: \(error)")
            let now = Date()
            let record = RunRecord.appFailure(trigger: trigger, provider: settings.provider, startedAt: now, endedAt: now,
                                              reason: Self.describe(error))
            appendRun(record)
            reloadRuns()
            if let text = NotificationText.afterRun(record, notifyOnSuccess: settings.notifyOnSuccess, strings: strings) { notifier.post(text) }
        }
    }

    private func runFinished(_ finished: Runner.Finished) {
        isRunning = false
        reloadAll()
        if let record = RunOutcome.record(runs, spawnedAt: finished.spawnedAt) {
            if let text = NotificationText.afterRun(record, notifyOnSuccess: settings.notifyOnSuccess, strings: strings) { notifier.post(text) }
        } else if finished.exitCode != 0 {
            notifier.post(.endedWithoutRecord(exitCode: finished.exitCode, strings: strings))
        }
        recomputeSchedule()
    }

    // MARK: Suggestions

    func answer(_ suggestion: Suggestion, _ answer: Answer, description: String?) {
        let id = suggestion.id
        writeSuggestion(id) { url in
            try SuggestionStore.answer(url, id: id, answer: answer, description: description, now: Date())
        }
    }

    func setNeverSuggest(_ suggestion: Suggestion, _ value: Bool) {
        let id = suggestion.id
        writeSuggestion(id) { url in try SuggestionStore.setNeverSuggest(url, id: id, value) }
    }

    // The store blocks on a file lock for up to 10 s, which must not freeze the menu bar window.
    private func writeSuggestion(_ id: String, _ write: @escaping (URL) throws -> Void) {
        guard !answering.contains(id) else { return }
        answering.insert(id)
        let url = paths.suggestions, attempts = Self.lockAttempts
        DispatchQueue.global(qos: .userInitiated).async {
            var failure: Error?
            for attempt in 1...attempts {
                do {
                    try write(url)
                    failure = nil
                    break
                } catch let error as FileLockError where attempt < attempts {
                    failure = error
                } catch {
                    failure = error
                    break
                }
            }
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    self.answering.remove(id)
                    if let failure { self.actionError = .saveAnswer(detail: Self.describe(failure)) }
                    self.reloadSuggestions()
                }
            }
        }
    }

    private static func describe(_ error: Error) -> String {
        switch error {
        case DecodingError.dataCorrupted(let context),
             DecodingError.keyNotFound(_, let context),
             DecodingError.typeMismatch(_, let context),
             DecodingError.valueNotFound(_, let context):
            let path = context.codingPath.map(\.stringValue).joined(separator: ".")
            return path.isEmpty ? context.debugDescription : "\(path): \(context.debugDescription)"
        default:
            return error.localizedDescription
        }
    }
}
