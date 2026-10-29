import Foundation

public struct FileLockError: LocalizedError, Equatable, CustomStringConvertible {
    public let message: String
    public var description: String { message }
    public var errorDescription: String? { message }
}

public enum FileLock {
    private static let retryInterval: useconds_t = 50_000

    // Same primitive as the Python side (flock LOCK_EX on the lock file), so both processes exclude each other.
    public static func withLock<T>(at url: URL, timeout: TimeInterval = 10, _ body: () throws -> T) throws -> T {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        let fd = open(url.path, O_CREAT | O_RDWR | O_CLOEXEC, AtomicFile.fileMode)
        guard fd >= 0 else { throw FileLockError(message: "Cannot open lock file \(url.path)") }
        defer { close(fd) }

        let deadline = Date().addingTimeInterval(timeout)
        while flock(fd, LOCK_EX | LOCK_NB) != 0 {
            guard errno == EWOULDBLOCK else { throw FileLockError(message: "flock failed on \(url.path)") }
            guard Date() < deadline else { throw FileLockError(message: "Timed out waiting for the lock \(url.lastPathComponent)") }
            usleep(retryInterval)
        }
        defer { flock(fd, LOCK_UN) }
        return try body()
    }
}
