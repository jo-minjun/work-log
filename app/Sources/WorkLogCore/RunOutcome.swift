import Foundation

public enum SlotDecision: Equatable {
    case run
    case skip(reason: String)

    public static let previousRunInProgress = "Previous run in progress"
    public static let slotPassed = "Slot passed"

    public static func decide(slot: Date, firedAt: Date, isRunning: Bool) -> SlotDecision {
        if isRunning { return .skip(reason: previousRunInProgress) }
        if ScheduleCalculator.isMissed(slot: slot, firedAt: firedAt) { return .skip(reason: slotPassed) }
        return .run
    }
}

public enum RunMark: Equatable {
    case none, warning, failure
}

public enum RunOutcome {
    // Skipped slots are not runs, so the menu bar mark and "Last run" look past them.
    public static func lastRun(_ runs: [RunRecord]) -> RunRecord? {
        runs.last { $0.result != .skipped }
    }

    public static func lastRunMark(_ runs: [RunRecord]) -> RunMark {
        guard let last = lastRun(runs) else { return .none }
        if last.result == .failed { return .failure }
        return last.hasWarnings ? .warning : .none
    }

    // The record run.sh wrote for a run the app started at `spawnedAt`. Skipped lines the app wrote meanwhile are ignored.
    public static func record(_ runs: [RunRecord], spawnedAt: Date) -> RunRecord? {
        let appReasons = [SlotDecision.previousRunInProgress, SlotDecision.slotPassed]
        // run.sh stamps whole seconds, so its start can read up to a second before the spawn.
        let earliest = spawnedAt.addingTimeInterval(-1)
        return runs.last { record in
            record.startedAt >= earliest && !(record.result == .skipped && appReasons.contains(record.reason ?? ""))
        }
    }

    // Counts suggestions that became pending since the last load; the first load only sets the baseline.
    public static func newPendingCount(previous: Set<String>?, current: Set<String>) -> Int {
        guard let previous else { return 0 }
        return current.subtracting(previous).count
    }
}

public struct NotificationText: Equatable {
    public var title: String
    public var body: String?

    public init(title: String, body: String? = nil) {
        self.title = title
        self.body = body
    }

    public static func afterRun(_ record: RunRecord, notifyOnSuccess: Bool, strings: UIStrings) -> NotificationText? {
        switch record.result {
        case .skipped:
            return nil
        case .failed:
            return NotificationText(title: strings.collectionFailed, body: record.reason)
        case .succeeded:
            guard notifyOnSuccess else { return nil }
            let title = record.hasWarnings ? strings.collectionFinishedWithWarnings : strings.collectionFinished
            return NotificationText(title: title, body: record.summary)
        }
    }

    // run.sh died before writing its line (for example zsh could not read it), so there is no record to show.
    public static func endedWithoutRecord(exitCode: Int32, strings: UIStrings) -> NotificationText {
        NotificationText(title: strings.collectionFailed, body: strings.endedWithoutRecord(exitCode))
    }

    public static func newSuggestions(_ count: Int, strings: UIStrings) -> NotificationText {
        NotificationText(title: strings.newSuggestions(count))
    }
}
