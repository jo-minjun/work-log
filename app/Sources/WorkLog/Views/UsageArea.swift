import SwiftUI
import WorkLogCore

struct UsageArea: View {
    @ObservedObject var model: AppModel
    @AppStorage("usageShowsPercent") private var showsPercent = true

    private var isCodex: Bool { model.settings.provider == .codex }

    var body: some View {
        let s = model.strings
        return VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(showsPercent ? percentTitle : monthSummary).font(.callout)
                Spacer()
                Picker("", selection: $showsPercent) {
                    Text(isCodex ? s.tokensLabel : "$").tag(false)
                    Text("%").tag(true)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .fixedSize()
            }
            if showsPercent { percentBody }
        }
        .padding(12)
    }

    private var percentTitle: String {
        let title = model.strings.usage(Format.provider(model.settings.provider))
        guard case .loaded(let snapshot) = model.usage, let updated = snapshot.updatedAt else { return title }
        return "\(title) · \(DisplayText.updatedAgo(updated, now: model.now, strings: model.strings))"
    }

    private var monthSummary: String {
        DisplayText.monthSummary(model.monthTotals, showsTokens: isCodex, strings: model.strings)
    }

    @ViewBuilder private var percentBody: some View {
        switch model.usage {
        case .noData:
            Muted(model.strings.noUsageData)
        case .unavailable:
            Muted(model.strings.unavailable)
        case .loaded(let snapshot):
            Meter(label: model.strings.session, window: snapshot.fiveHour, now: model.now, strings: model.strings)
            Meter(label: model.strings.weekly, window: snapshot.weekly, now: model.now, strings: model.strings)
        }
    }
}

private struct Meter: View {
    let label: String
    let window: UsageWindow?
    let now: Date
    let strings: UIStrings

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(label).font(.caption)
                Spacer()
                if let window { Muted(DisplayText.resetsIn(window.resetsAt, now: now, strings: strings)) }
            }
            if let window {
                ProgressView(value: min(max(window.usedPercent, 0), 100), total: 100)
                Muted(strings.percentUsed(Int(window.usedPercent.rounded())))
            } else {
                Muted(strings.unavailable)
            }
        }
    }
}
