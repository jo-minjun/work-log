import Foundation

// Python writes offsets like +09:00 with or without fractional seconds; accept both.
public enum ISODate {
    // Parsing reads the offset from the text, so shared formatters are safe; they are never changed after creation.
    private static let plain = ISO8601DateFormatter()
    private static let fractional: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()

    public static func parse(_ text: String) -> Date? {
        plain.date(from: text) ?? fractional.date(from: text)
    }

    // A new formatter each time: the system time zone can change while the app runs, and this is called off the main thread.
    public static func format(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.timeZone = .current
        return formatter.string(from: date)
    }
}
