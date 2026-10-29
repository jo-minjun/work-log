import SwiftUI
import WorkLogCore

struct HistoryTab: View {
    private static let shownRuns = 50

    @ObservedObject var model: AppModel

    var body: some View {
        let s = model.strings
        return VStack(alignment: .leading, spacing: 8) {
            Text(s.runs).bold()
            if model.runs.isEmpty { Muted(s.noRuns) }
            ForEach(Array(model.runs.suffix(Self.shownRuns).reversed().enumerated()), id: \.offset) { _, run in
                HStack(alignment: .firstTextBaseline) {
                    Text(DisplayText.time(run.startedAt, now: model.now, strings: s)).font(.caption).monospacedDigit()
                    Spacer()
                    Text(resultText(run)).font(.caption).foregroundStyle(color(run)).lineLimit(1).truncationMode(.tail)
                }
            }

            Text(s.suggestionsAndAnswers).bold().padding(.top, 8)
            if model.pastSuggestions.isEmpty { Muted(s.noAnswers) }
            ForEach(model.pastSuggestions) { suggestion in
                Card {
                    HStack {
                        Text(suggestion.name).bold()
                        Spacer()
                        if let answered = answeredAt(suggestion) { Muted(s.answeredOn(DisplayText.day(answered, strings: s))) }
                    }
                    Muted(statusLine(suggestion))
                    Toggle(s.neverSuggest, isOn: Binding(
                        get: { suggestion.neverSuggest },
                        set: { model.setNeverSuggest(suggestion, $0) }
                    ))
                    .toggleStyle(.switch)
                    .controlSize(.mini)
                    .font(.caption)
                    .disabled(model.answering.contains(suggestion.id))
                }
            }
        }
    }

    private func resultText(_ run: RunRecord) -> String {
        let s = model.strings
        switch run.result {
        case .succeeded:
            let word = run.hasWarnings ? s.succeededWithWarnings : s.succeeded
            if let cost = run.costUsd { return "\(word) \(DisplayText.cost(cost))" }
            if let tokens = run.tokens { return "\(word) \(DisplayText.tokens(tokens, strings: s))" }
            return word
        case .failed:
            return run.reason.map { "\(s.failed) · \($0)" } ?? s.failed
        case .skipped:
            return run.reason.map { "\(s.skipped) · \($0)" } ?? s.skipped
        }
    }

    private func color(_ run: RunRecord) -> Color {
        switch run.result {
        case .succeeded: run.hasWarnings ? .orange : .green
        case .failed: .red
        case .skipped: .secondary
        }
    }

    private func answerWord(_ answer: String) -> String {
        answer == "accept" ? model.strings.answerAdded : model.strings.answerRejected
    }

    private func answeredAt(_ suggestion: Suggestion) -> Date? {
        suggestion.pendingAnswer?.answeredAt ?? suggestion.history.last.flatMap { ISODate.parse($0.answeredAt) }
    }

    private func statusLine(_ suggestion: Suggestion) -> String {
        if let pending = suggestion.pendingAnswer {
            return model.strings.waitingForNextCollection(answerWord(pending.answer))
        }
        guard let last = suggestion.history.last else { return "" }
        let applied = last.appliedAt.flatMap(ISODate.parse).map { model.strings.appliedAt(DisplayText.time($0, now: model.now, strings: model.strings)) } ?? ""
        return "\(answerWord(last.answer))\(applied)"
    }
}
