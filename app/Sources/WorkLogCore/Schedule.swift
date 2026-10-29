import Foundation

public enum ScheduleCalculator {
    public static let missedGrace: TimeInterval = 120
    static let lookAhead: TimeInterval = 48 * 3600

    public static func nextRun(_ settings: AppSettings, after now: Date, calendar: Calendar) -> Date? {
        settings.scheduleEnabled ? nextRun(settings.schedule, after: now, calendar: calendar) : nil
    }

    public static func nextRun(_ schedule: AppSettings.Schedule, after now: Date, calendar: Calendar) -> Date? {
        let startOfToday = calendar.startOfDay(for: now)
        let horizon = now.addingTimeInterval(lookAhead)
        var best: Date?
        // Start one day back: a cycle begun yesterday can run past midnight into today.
        for offset in -1...2 {
            guard let day = calendar.date(byAdding: .day, value: offset, to: startOfToday) else { continue }
            for (dayShift, minutes) in cycleSlots(schedule) {
                guard let slotDay = calendar.date(byAdding: .day, value: dayShift, to: day),
                      // For a local time skipped by DST, .strict returns the same time on the next day. That date is
                      // also the next day's own slot, so the skipped slot simply does not appear.
                      let slot = calendar.date(
                        bySettingHour: minutes / 60, minute: minutes % 60, second: 0, of: slotDay, matchingPolicy: .strict
                      ), slot > now, slot <= horizon, !isQuiet(slot, schedule.quietRanges, calendar) else { continue }
                if best == nil || slot < best! { best = slot }
            }
        }
        return best
    }

    public static func isMissed(slot: Date, firedAt: Date) -> Bool {
        firedAt.timeIntervalSince(slot) > missedGrace
    }

    // Slots of the cycle that starts on a given day, as (days after that day, minute of day).
    private static func cycleSlots(_ schedule: AppSettings.Schedule) -> [(Int, Int)] {
        switch schedule.mode {
        case .times:
            return schedule.times.map { (0, $0.minutesOfDay) }
        case .interval:
            let step = schedule.interval.hours * 60
            let anchor = schedule.interval.anchor.minutesOfDay
            // The cycle ends before the next day's anchor, so k * step stays under 24 h.
            return stride(from: 0, to: 24 * 60, by: step).map {
                let total = anchor + $0
                return (total / (24 * 60), total % (24 * 60))
            }
        }
    }

    // Start is inclusive, end is exclusive; start > end means the range crosses midnight.
    private static func isQuiet(_ slot: Date, _ ranges: [AppSettings.Schedule.QuietRange], _ calendar: Calendar) -> Bool {
        let parts = calendar.dateComponents([.hour, .minute], from: slot)
        let minute = (parts.hour ?? 0) * 60 + (parts.minute ?? 0)
        return ranges.contains { range in
            let start = range.start.minutesOfDay, end = range.end.minutesOfDay
            if start == end { return false }
            return start < end ? (minute >= start && minute < end) : (minute >= start || minute < end)
        }
    }
}
