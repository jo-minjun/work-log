import Foundation

public enum DisplayText {
    private static let cacheLock = NSLock()
    nonisolated(unsafe) private static var formatters: [String: DateFormatter] = [:]

    public static func cost(_ usd: Double) -> String {
        String(format: "$%.2f", usd)
    }

    public static func tokens(_ count: Int, strings: UIStrings) -> String {
        let formatter = NumberFormatter()
        formatter.locale = strings.locale
        formatter.numberStyle = .decimal
        return strings.tokenCount(formatter.string(from: NSNumber(value: count)) ?? String(count))
    }

    public static func runs(_ count: Int, strings: UIStrings) -> String {
        strings.runCount(count)
    }

    public static func monthSummary(_ totals: MonthTotals, showsTokens: Bool, strings: UIStrings) -> String {
        let head = strings.thisMonth(runs(totals.runs, strings: strings))
        if showsTokens { return "\(head), \(tokens(totals.tokens, strings: strings))" }
        let missing = totals.runsWithoutCost > 0 ? " \(strings.withoutCostData(totals.runsWithoutCost))" : ""
        return "\(head), \(cost(totals.costUsd))\(missing)"
    }

    public static func updatedAgo(_ updatedAt: Date, now: Date, strings: UIStrings) -> String {
        let minutes = max(0, Int(now.timeIntervalSince(updatedAt) / 60))
        if minutes < 60 { return strings.minutesAgo(minutes) }
        let hours = minutes / 60
        if hours < 48 { return strings.hoursAgo(hours) }
        return strings.daysAgo(hours / 24)
    }

    public static func resetsIn(_ resetsAt: Date, now: Date, strings: UIStrings) -> String {
        let minutes = Int(resetsAt.timeIntervalSince(now) / 60)
        guard minutes > 0 else { return strings.resetPassed }
        let days = minutes / (24 * 60), hours = (minutes / 60) % 24, rest = minutes % 60
        if days > 0 { return strings.resetsInDays(days, hours) }
        if hours > 0 { return strings.resetsInHours(hours, rest) }
        return strings.resetsInMinutes(rest)
    }

    // Today shows only the clock; other days add the date so "14:46" is never ambiguous.
    public static func time(_ date: Date, now: Date, strings: UIStrings, calendar: Calendar = .current) -> String {
        string(date, calendar.isDate(date, inSameDayAs: now) ? "HH:mm" : "MM/dd HH:mm", strings, calendar)
    }

    public static func nextRun(_ date: Date, now: Date, strings: UIStrings, calendar: Calendar = .current) -> String {
        strings.nextRun(string(date, calendar.isDate(date, inSameDayAs: now) ? "HH:mm" : "EEE HH:mm", strings, calendar))
    }

    public static func day(_ date: Date, strings: UIStrings, calendar: Calendar = .current) -> String {
        string(date, "MM/dd", strings, calendar)
    }

    // Views redraw often, so one formatter per locale and pattern is kept. The zone is set on every use because
    // the system time zone can change while the app runs.
    private static func string(_ date: Date, _ pattern: String, _ strings: UIStrings, _ calendar: Calendar) -> String {
        let locale = strings.locale
        let key = "\(locale.identifier) \(pattern)"
        cacheLock.lock()
        defer { cacheLock.unlock() }
        let formatter = formatters[key] ?? {
            let formatter = DateFormatter()
            formatter.locale = locale
            formatter.dateFormat = pattern
            formatters[key] = formatter
            return formatter
        }()
        formatter.timeZone = calendar.timeZone
        return formatter.string(from: date)
    }
}
