import Foundation

public struct ProcessGroupError: LocalizedError, Equatable, CustomStringConvertible {
    public let message: String
    public var description: String { message }
    public var errorDescription: String? { message }
}

// The child leads its own process group, so one signal reaches run.sh and every tool it started.
public enum ProcessGroup {
    public static func spawn(_ executable: String, arguments: [String], environment: [String: String], outputPath: String) throws -> pid_t {
        var attr: posix_spawnattr_t?
        posix_spawnattr_init(&attr)
        defer { posix_spawnattr_destroy(&attr) }
        // CLOEXEC_DEFAULT keeps the app's own descriptors out of the child; SETSIGDEF/SETSIGMASK give it a clean signal state.
        let flags = POSIX_SPAWN_SETPGROUP | POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSIGDEF | POSIX_SPAWN_SETSIGMASK
        posix_spawnattr_setflags(&attr, Int16(flags))
        posix_spawnattr_setpgroup(&attr, 0)
        var allSignals = sigset_t()
        sigfillset(&allSignals)
        posix_spawnattr_setsigdefault(&attr, &allSignals)
        var noSignals = sigset_t()
        sigemptyset(&noSignals)
        posix_spawnattr_setsigmask(&attr, &noSignals)

        var actions: posix_spawn_file_actions_t?
        posix_spawn_file_actions_init(&actions)
        defer { posix_spawn_file_actions_destroy(&actions) }
        posix_spawn_file_actions_addopen(&actions, STDIN_FILENO, "/dev/null", O_RDONLY, 0)
        posix_spawn_file_actions_addopen(&actions, STDOUT_FILENO, outputPath, O_WRONLY | O_CREAT | O_APPEND, AtomicFile.fileMode)
        posix_spawn_file_actions_adddup2(&actions, STDOUT_FILENO, STDERR_FILENO)

        let argv = ([executable] + arguments).map { strdup($0) } + [nil]
        let envp = environment.map { strdup("\($0.key)=\($0.value)") } + [nil]
        defer {
            argv.forEach { free($0) }
            envp.forEach { free($0) }
        }
        var pid: pid_t = 0
        let code = posix_spawn(&pid, executable, &actions, &attr, argv, envp)
        guard code == 0 else { throw ProcessGroupError(message: "Cannot start \(executable): \(String(cString: strerror(code)))") }
        return pid
    }

    // Blocks until the child exits and returns its exit code (128 + signal when killed by a signal).
    public static func wait(_ pid: pid_t) -> Int32 {
        var status: Int32 = 0
        while waitpid(pid, &status, 0) == -1 {
            if errno != EINTR { return -1 }
        }
        let signal = status & 0x7f
        return signal == 0 ? (status >> 8) & 0xff : 128 + signal
    }

    public static func terminate(_ pgid: pid_t) {
        killpg(pgid, SIGTERM)
    }
}
