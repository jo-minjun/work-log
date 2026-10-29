import Foundation

struct AppPaths {
    static let skillPathInfoKey = "WorkLogSkillPath"
    static let skillPathEnv = "WORKLOG_SKILL_PATH"
    static let extraPathInfoKey = "WorkLogExtraPath"
    static let extraPathEnv = "WORKLOG_EXTRA_PATH"
    // The log and data folders hold raw transcripts and the Slack identity.
    static let privateDirectoryMode = 0o700

    let dataDir: URL
    let logDir: URL
    let codexSessions: URL
    let skillDir: URL?
    // Folders of python3, claude and codex in the user's shell, recorded by install.sh; run.sh puts them first in PATH.
    let extraPath: String?

    var settings: URL { dataDir.appendingPathComponent("settings.json") }
    var suggestions: URL { dataDir.appendingPathComponent("suggestions.json") }
    var runs: URL { dataDir.appendingPathComponent("runs.jsonl") }
    var claudeRateLimits: URL { dataDir.appendingPathComponent("claude-rate-limits.json") }
    var lockDir: URL { logDir.appendingPathComponent(".lock") }
    var runnerOutput: URL { logDir.appendingPathComponent("app-runner.log") }
    var runScript: URL? { skillDir?.appendingPathComponent("scripts/run.sh") }

    // Same overrides as run.sh and the Python scripts, so a test environment never touches real data.
    static func current(environment: [String: String] = ProcessInfo.processInfo.environment) -> AppPaths {
        let home = FileManager.default.homeDirectoryForCurrentUser
        func dir(_ key: String, _ fallback: String) -> URL {
            if let value = environment[key], !value.isEmpty { return URL(fileURLWithPath: (value as NSString).expandingTildeInPath) }
            return home.appendingPathComponent(fallback)
        }
        return AppPaths(
            dataDir: dir("WORKLOG_HOME", "Library/Application Support/WorkLog"),
            logDir: dir("WORKLOG_LOG_DIR", "Library/Logs/work-log"),
            codexSessions: home.appendingPathComponent(".codex/sessions"),
            skillDir: bundleValue(skillPathInfoKey, orEnv: skillPathEnv, environment)
                .map { URL(fileURLWithPath: ($0 as NSString).expandingTildeInPath) },
            extraPath: bundleValue(extraPathInfoKey, orEnv: extraPathEnv, environment)
        )
    }

    // The bundled app reads what install.sh wrote into Info.plist; `swift run` has no bundle and uses the environment.
    private static func bundleValue(_ key: String, orEnv env: String, _ environment: [String: String]) -> String? {
        let raw = AppEnvironment.isBundled ? Bundle.main.object(forInfoDictionaryKey: key) as? String : environment[env]
        guard let raw, !raw.isEmpty else { return nil }
        return raw
    }
}

enum AppEnvironment {
    // `swift run` has no bundle; UNUserNotificationCenter crashes and SMAppService has nothing to register there.
    static var isBundled: Bool { Bundle.main.bundleIdentifier != nil }

    // NSLog reaches both stderr (swift run) and the unified log (Console.app) for the bundled app.
    static func log(_ message: String) {
        NSLog("WorkLog: %@", message)
    }
}
