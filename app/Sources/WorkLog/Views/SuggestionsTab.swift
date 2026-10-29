import SwiftUI
import WorkLogCore

struct SuggestionsTab: View {
    @ObservedObject var model: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Muted(model.strings.answersApplyNext)
            if model.pendingSuggestions.isEmpty {
                Muted(model.strings.noSuggestions)
            }
            ForEach(model.pendingSuggestions) { suggestion in
                SuggestionCard(model: model, suggestion: suggestion)
            }
        }
    }
}

private struct SuggestionCard: View {
    private static let shownEvidence = 5

    @ObservedObject var model: AppModel
    let suggestion: Suggestion
    @State private var draft: String

    init(model: AppModel, suggestion: Suggestion) {
        self.model = model
        self.suggestion = suggestion
        _draft = State(initialValue: suggestion.description)
    }

    private var evidenceSummary: String {
        let days = Set(suggestion.evidence.map(\.date)).sorted()
        let span = days.count > 1 ? "\(Format.evidenceDay(days[0])) – \(Format.evidenceDay(days[days.count - 1]))" : days.first.map(Format.evidenceDay) ?? ""
        let counts = model.strings.evidenceCounts(days.count, suggestion.evidence.count)
        return span.isEmpty ? counts : "\(span) · \(counts)"
    }

    var body: some View {
        let s = model.strings
        return Card {
            Text(s.newProject(suggestion.name)).bold()
            Muted(evidenceSummary)
            ForEach(Array(suggestion.evidence.prefix(Self.shownEvidence).enumerated()), id: \.offset) { _, item in
                Text("• \(item.line)").font(.caption).fixedSize(horizontal: false, vertical: true)
            }
            if suggestion.evidence.count > Self.shownEvidence {
                Muted(s.moreEvidence(suggestion.evidence.count - Self.shownEvidence))
            }
            TextField(s.description, text: $draft, axis: .vertical)
                .textFieldStyle(.roundedBorder)
                .font(.caption)
                .lineLimit(2...4)
            HStack {
                Button(s.add) { model.answer(suggestion, .accept, description: trimmedDraft) }
                    .buttonStyle(.borderedProminent)
                Button(s.reject) { model.answer(suggestion, .reject, description: nil) }
                Button(s.neverSuggest) { model.answer(suggestion, .never, description: nil) }
                    .foregroundStyle(.red)
            }
            .controlSize(.small)
            .disabled(model.answering.contains(suggestion.id))
        }
        // A collector update replaces the description; follow it unless the user already edited the draft.
        .onChange(of: suggestion.description) { old, new in
            if draft == old { draft = new }
        }
    }

    private var trimmedDraft: String? {
        let text = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }
}
