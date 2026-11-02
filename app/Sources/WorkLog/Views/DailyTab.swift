import SwiftUI
import WorkLogCore

struct DailyTab: View {
    private static let copiedFeedback: TimeInterval = 1.5

    @ObservedObject var model: AppModel
    @State private var copies = 0
    @State private var showEvidence = false

    private var s: UIStrings { model.strings }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            header
            if let message = model.dailyFailureMessage {
                Text(message).font(.caption).foregroundStyle(.red).fixedSize(horizontal: false, vertical: true)
            }
            if let daily = model.daily {
                Card {
                    Text(daily.text)
                        .font(.callout)
                        .textSelection(.enabled)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack {
                        Spacer()
                        Button(copies > 0 ? s.copied : s.copy) {
                            model.copyDaily()
                            copies += 1
                        }
                        .buttonStyle(.borderedProminent)
                        .controlSize(.small)
                        // A new copy restarts the wait, so the label always stays for the full time
                        .task(id: copies) {
                            guard copies > 0 else { return }
                            try? await Task.sleep(for: .seconds(Self.copiedFeedback))
                            if !Task.isCancelled { copies = 0 }
                        }
                    }
                }
                evidence(daily)
                ForEach(Array(daily.notes.enumerated()), id: \.offset) { Muted($0.element) }
                ForEach(daily.sourceProblems, id: \.source) { Muted("\($0.source): \($0.status)") }
            } else {
                Muted(s.noDaily)
            }
        }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 2) {
                Text(model.daily.map { DailyFormat.title($0, strings: s) } ?? s.tabDaily).bold()
                if let time = model.daily.flatMap({ DailyFormat.time($0.generatedAt) }) {
                    Muted(s.generatedAt(time))
                }
            }
            Spacer()
            if let started = model.dailyStartedAt {
                ProgressView().controlSize(.small)
                TimelineView(.periodic(from: started, by: 1)) { context in
                    Muted(Self.elapsed(from: started, to: context.date))
                }
                Button(s.stop) { model.stopDaily() }.controlSize(.small)
            } else {
                Button(s.generateNow) { model.generateDaily() }
                    .controlSize(.small)
                    .disabled(model.settingsError != nil)
            }
        }
    }

    private func evidence(_ daily: Daily) -> some View {
        DisclosureGroup(s.evidenceCount(daily.evidence.count), isExpanded: $showEvidence) {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(daily.evidence.enumerated()), id: \.offset) { _, entry in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.task).font(.caption).bold().fixedSize(horizontal: false, vertical: true)
                        Muted(([entry.reason, entry.sources.joined(separator: ", ")] + (entry.weak ? [s.weak] : []))
                            .filter { !$0.isEmpty }.joined(separator: " · "))
                        ForEach(entry.links.compactMap(Self.webURL), id: \.self) { url in
                            Link(url.absoluteString, destination: url).font(.caption).lineLimit(1).truncationMode(.middle)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.top, 4)
        }
        .font(.caption)
    }

    // Links come from collected text, so only web links are made clickable.
    private static func webURL(_ text: String) -> URL? {
        guard let url = URL(string: text), ["http", "https"].contains(url.scheme?.lowercased() ?? "") else { return nil }
        return url
    }

    private static func elapsed(from start: Date, to now: Date) -> String {
        let seconds = max(0, Int(now.timeIntervalSince(start)))
        return String(format: "%d:%02d", seconds / 60, seconds % 60)
    }
}
