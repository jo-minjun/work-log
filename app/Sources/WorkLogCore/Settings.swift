import Foundation

public struct ClockTime: Codable, Equatable, Hashable {
    public var hour: Int
    public var minute: Int

    public init(hour: Int, minute: Int) {
        self.hour = hour
        self.minute = minute
    }

    public init?(string: String) {
        let parts = string.split(separator: ":", omittingEmptySubsequences: false)
        guard parts.count == 2, parts[0].count == 2, parts[1].count == 2,
              let h = Int(parts[0]), let m = Int(parts[1]),
              (0..<24).contains(h), (0..<60).contains(m) else { return nil }
        self.init(hour: h, minute: m)
    }

    public var minutesOfDay: Int { hour * 60 + minute }
    public var string: String { String(format: "%02d:%02d", hour, minute) }

    public init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        guard let value = ClockTime(string: raw) else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Invalid HH:MM: \(raw)"))
        }
        self = value
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(string)
    }
}

public struct AppSettings: Codable, Equatable {
    public struct Schedule: Codable, Equatable {
        public enum Mode: String, Codable, Equatable {
            case times, interval
        }

        public struct Interval: Codable, Equatable {
            public var hours: Int
            public var anchor: ClockTime

            public init(hours: Int, anchor: ClockTime) {
                // The schedule strides by hours, so 0 or less would never end; the decoder and the UI keep it in range.
                precondition((1...24).contains(hours), "Interval hours must be 1-24, got \(hours)")
                self.hours = hours
                self.anchor = anchor
            }

            public init(from decoder: Decoder) throws {
                let c = try decoder.container(keyedBy: CodingKeys.self)
                let d = AppSettings.defaults.schedule.interval
                hours = try c.decodeIfPresent(Int.self, forKey: .hours) ?? d.hours
                guard (1...24).contains(hours) else {
                    throw DecodingError.dataCorruptedError(
                        forKey: .hours, in: c, debugDescription: "Interval hours must be 1-24, got \(hours)")
                }
                anchor = try c.decodeIfPresent(ClockTime.self, forKey: .anchor) ?? d.anchor
            }
        }

        public struct QuietRange: Codable, Equatable {
            public var start: ClockTime
            public var end: ClockTime

            public init(start: ClockTime, end: ClockTime) {
                self.start = start
                self.end = end
            }
        }

        public var mode: Mode
        public var times: [ClockTime]
        public var interval: Interval
        public var quietRanges: [QuietRange]

        public init(mode: Mode, times: [ClockTime], interval: Interval, quietRanges: [QuietRange]) {
            self.mode = mode
            self.times = times
            self.interval = interval
            self.quietRanges = quietRanges
        }

        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            let d = AppSettings.defaults.schedule
            mode = try c.decodeIfPresent(Mode.self, forKey: .mode) ?? d.mode
            times = try c.decodeIfPresent([ClockTime].self, forKey: .times) ?? d.times
            interval = try c.decodeIfPresent(Interval.self, forKey: .interval) ?? d.interval
            quietRanges = try c.decodeIfPresent([QuietRange].self, forKey: .quietRanges) ?? d.quietRanges
        }
    }

    public enum Provider: String, Codable, Equatable, Sendable {
        case claude, codex
    }

    public enum Language: String, Codable, Equatable {
        case en, ko
    }

    // Owned by the Python collector; the app only carries it through unchanged.
    public struct Slack: Codable, Equatable {
        public var userId: String?
        public var displayName: String?
        public var checkedAt: String?

        public init(userId: String? = nil, displayName: String? = nil, checkedAt: String? = nil) {
            self.userId = userId
            self.displayName = displayName
            self.checkedAt = checkedAt
        }
    }

    public var version: Int
    public var schedule: Schedule
    public var provider: Provider
    public var logFolder: String
    public var logLanguage: Language
    // The language of the app's own UI; logLanguage is the language of the log files.
    public var appLanguage: Language
    public var sessionFolders: [String]
    public var launchAtLogin: Bool
    public var notifyOnSuccess: Bool
    // Scheduled runs spend money, so a fresh install waits for the user to start the schedule.
    public var scheduleEnabled: Bool
    public var slack: Slack?

    public init(
        version: Int, schedule: Schedule, provider: Provider, logFolder: String, logLanguage: Language, appLanguage: Language,
        sessionFolders: [String], launchAtLogin: Bool, notifyOnSuccess: Bool, scheduleEnabled: Bool, slack: Slack?
    ) {
        self.version = version
        self.schedule = schedule
        self.provider = provider
        self.logFolder = logFolder
        self.logLanguage = logLanguage
        self.appLanguage = appLanguage
        self.sessionFolders = sessionFolders
        self.launchAtLogin = launchAtLogin
        self.notifyOnSuccess = notifyOnSuccess
        self.scheduleEnabled = scheduleEnabled
        self.slack = slack
    }

    public static let defaults = AppSettings(
        version: 1,
        schedule: Schedule(
            mode: .times,
            times: [ClockTime(hour: 10, minute: 0), ClockTime(hour: 22, minute: 0)],
            interval: .init(hours: 4, anchor: ClockTime(hour: 8, minute: 0)),
            quietRanges: []
        ),
        provider: .claude,
        logFolder: "~/WorkLog",
        logLanguage: .en,
        appLanguage: .en,
        sessionFolders: [],
        launchAtLogin: true,
        notifyOnSuccess: true,
        scheduleEnabled: false,
        slack: nil
    )

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let d = AppSettings.defaults
        version = try c.decodeIfPresent(Int.self, forKey: .version) ?? d.version
        schedule = try c.decodeIfPresent(Schedule.self, forKey: .schedule) ?? d.schedule
        provider = try c.decodeIfPresent(Provider.self, forKey: .provider) ?? d.provider
        logFolder = try c.decodeIfPresent(String.self, forKey: .logFolder) ?? d.logFolder
        logLanguage = try c.decodeIfPresent(Language.self, forKey: .logLanguage) ?? d.logLanguage
        appLanguage = try c.decodeIfPresent(Language.self, forKey: .appLanguage) ?? d.appLanguage
        sessionFolders = try c.decodeIfPresent([String].self, forKey: .sessionFolders) ?? d.sessionFolders
        launchAtLogin = try c.decodeIfPresent(Bool.self, forKey: .launchAtLogin) ?? d.launchAtLogin
        notifyOnSuccess = try c.decodeIfPresent(Bool.self, forKey: .notifyOnSuccess) ?? d.notifyOnSuccess
        // Only the app writes `version`. A file with it but without this key comes from an install whose
        // schedule was already running; a file without it was created by the collector before the app ever saved.
        scheduleEnabled = try c.decodeIfPresent(Bool.self, forKey: .scheduleEnabled) ?? c.contains(.version)
        slack = try c.decodeIfPresent(Slack.self, forKey: .slack)
    }
}
