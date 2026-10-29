import Foundation
import WorkLogCore

struct RunnerError: LocalizedError {
    let errorDescription: String?
}

// Runs run.sh one at a time. run.sh writes the runs.jsonl line; the Runner only reports when the process ends.
@MainActor
final class Runner {
    struct Finished {
        let spawnedAt: Date
        let exitCode: Int32
    }

    struct Current {
        let pid: pid_t
        let spawnedAt: Date
        let trigger: RunRecord.Trigger
        let provider: AppSettings.Provider
    }

    private let paths: AppPaths
    private var current: Current?
    var onFinish: ((Finished) -> Void)?

    init(paths: AppPaths) {
        self.paths = paths
    }

    var isRunning: Bool { current != nil }

    func start(trigger: RunRecord.Trigger, provider: AppSettings.Provider) throws {
        guard !isRunning else { return }
        // zsh reads the script, so it does not need the executable bit.
        guard let script = paths.runScript, FileManager.default.fileExists(atPath: script.path) else {
            throw RunnerError(errorDescription: "run.sh not found. Check the skill path (\(paths.runScript?.path ?? "not set")).")
        }
        try FileManager.default.createDirectory(at: paths.logDir, withIntermediateDirectories: true,
                                                attributes: [.posixPermissions: AppPaths.privateDirectoryMode])
        var environment = ProcessInfo.processInfo.environment
        environment["WORKLOG_TRIGGER"] = trigger.rawValue
        if let extra = paths.extraPath { environment[AppPaths.extraPathEnv] = extra }
        let started = Date()
        let child = try ProcessGroup.spawn("/bin/zsh", arguments: [script.path], environment: environment,
                                           outputPath: paths.runnerOutput.path)
        current = Current(pid: child, spawnedAt: started, trigger: trigger, provider: provider)
        DispatchQueue.global(qos: .utility).async {
            let code = ProcessGroup.wait(child)
            DispatchQueue.main.async {
                MainActor.assumeIsolated { self.finished(child, code) }
            }
        }
    }

    // On SIGTERM run.sh removes only its working directory, so the app removes the lock here and the next run can start at once.
    // Returns the stopped run once; a second call (quit, then applicationWillTerminate) does nothing.
    func terminate() -> Current? {
        guard let stopped = current else { return nil }
        current = nil
        ProcessGroup.terminate(stopped.pid)
        try? FileManager.default.removeItem(at: paths.lockDir)
        return stopped
    }

    private func finished(_ child: pid_t, _ code: Int32) {
        guard let run = current, run.pid == child else { return }
        current = nil
        onFinish?(Finished(spawnedAt: run.spawnedAt, exitCode: code))
    }
}
