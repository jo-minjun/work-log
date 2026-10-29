import Foundation

// Atomic replaces swap the inode, so a source on the file alone goes deaf after the first write.
// The directory source catches creates and renames; per-file sources catch in-place appends (runs.jsonl).
// Events only wake the watcher; a stat comparison decides which files really changed, so a busy
// claude-rate-limits.json does not make the app re-read everything else.
@MainActor
final class FileWatcher {
    private struct Stamp: Equatable {
        var inode: UInt64
        var size: Int64
        var modified: timespec

        static func == (a: Stamp, b: Stamp) -> Bool {
            a.inode == b.inode && a.size == b.size && a.modified.tv_sec == b.modified.tv_sec && a.modified.tv_nsec == b.modified.tv_nsec
        }
    }

    private static let debounce: TimeInterval = 0.3

    private let directory: URL
    private let names: [String]
    private let onChange: (Set<String>) -> Void
    private var directorySource: DispatchSourceFileSystemObject?
    private var fileSources: [String: DispatchSourceFileSystemObject] = [:]
    private var stamps: [String: Stamp] = [:]
    private var pending: DispatchWorkItem?

    init(directory: URL, names: [String], onChange: @escaping (Set<String>) -> Void) {
        self.directory = directory
        self.names = names
        self.onChange = onChange
    }

    func start() {
        for name in names { stamps[name] = stamp(name) }
        directorySource = makeSource(directory.path, [.write]) { [weak self] _ in
            self?.names.forEach { self?.watch($0) }
            self?.changed()
        }
        names.forEach { watch($0) }
    }

    private func watch(_ name: String) {
        fileSources.removeValue(forKey: name)?.cancel()
        fileSources[name] = makeSource(directory.appendingPathComponent(name).path, [.write, .extend, .delete, .rename]) { [weak self] event in
            if !event.isDisjoint(with: [.delete, .rename]) { self?.watch(name) }
            self?.changed()
        }
    }

    private func makeSource(_ path: String, _ mask: DispatchSource.FileSystemEvent, _ handler: @escaping @MainActor (DispatchSource.FileSystemEvent) -> Void)
        -> DispatchSourceFileSystemObject? {
        let fd = open(path, O_EVTONLY)
        guard fd >= 0 else { return nil }
        let source = DispatchSource.makeFileSystemObjectSource(fileDescriptor: fd, eventMask: mask, queue: .main)
        source.setEventHandler { [unowned source] in
            let event = source.data
            MainActor.assumeIsolated { handler(event) }
        }
        source.setCancelHandler { close(fd) }
        source.resume()
        return source
    }

    private func changed() {
        pending?.cancel()
        let work = DispatchWorkItem { [weak self] in MainActor.assumeIsolated { self?.report() } }
        pending = work
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.debounce, execute: work)
    }

    private func report() {
        var changed = Set<String>()
        for name in names {
            let current = stamp(name)
            if current != stamps[name] { changed.insert(name) }
            stamps[name] = current
        }
        if !changed.isEmpty { onChange(changed) }
    }

    private func stamp(_ name: String) -> Stamp? {
        var info = stat()
        guard stat(directory.appendingPathComponent(name).path, &info) == 0 else { return nil }
        return Stamp(inode: info.st_ino, size: info.st_size, modified: info.st_mtimespec)
    }
}
