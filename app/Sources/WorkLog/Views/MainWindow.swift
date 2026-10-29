import SwiftUI

struct MainWindow: View {
    enum Tab: Hashable {
        case suggestions, history, settings
    }

    private static let width: CGFloat = 340
    // A menu bar window that changes size is re-anchored to its status item. When a menu bar manager
    // such as Ice has moved the item off screen, the window follows it, so the height never changes.
    private static let height: CGFloat = 600

    @ObservedObject var model: AppModel
    @State private var tab: Tab = .suggestions

    var body: some View {
        let s = model.strings
        return VStack(spacing: 0) {
            banners
            StatusArea(model: model)
            Divider()
            UsageArea(model: model)
            Divider()
            tabBar
            Divider()
            ScrollView {
                Group {
                    switch tab {
                    case .suggestions: SuggestionsTab(model: model)
                    case .history: HistoryTab(model: model)
                    case .settings: SettingsTab(model: model)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(12)
            }
            .frame(maxHeight: .infinity)
            Divider()
            HStack {
                Muted("WorkLog")
                Spacer()
                Button(s.quit) { model.quit() }.controlSize(.small)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
        }
        .frame(width: Self.width, height: Self.height)
        // Until the schedule is on, the window opens on Settings so they are checked before the first scheduled run.
        .onAppear { if !model.settings.scheduleEnabled { tab = .settings } }
    }

    @ViewBuilder private var banners: some View {
        if let message = model.settingsErrorMessage {
            Banner(message: message, actionTitle: model.strings.backUpAndReset) { model.backUpAndReset(.settings) }
            Divider()
        }
        if let message = model.suggestionsErrorMessage {
            Banner(message: message, actionTitle: model.strings.backUpAndReset) { model.backUpAndReset(.suggestions) }
            Divider()
        }
        if let message = model.actionErrorMessage {
            Banner(message: message, actionTitle: model.strings.dismiss) { model.actionError = nil }
            Divider()
        }
    }

    private var tabBar: some View {
        HStack(spacing: 4) {
            tabButton(.suggestions, model.strings.tabSuggestions, badge: model.pendingSuggestions.count)
            tabButton(.history, model.strings.tabHistory)
            tabButton(.settings, model.strings.tabSettings)
        }
        .padding([.horizontal, .top], 8)
    }

    private func tabButton(_ value: Tab, _ title: String, badge: Int = 0) -> some View {
        let selected = tab == value
        return Button { tab = value } label: {
            HStack(spacing: 4) {
                Text(title)
                    .fontWeight(selected ? .semibold : .regular)
                    .foregroundStyle(selected ? .primary : .secondary)
                if badge > 0 {
                    Text("\(badge)")
                        .font(.caption2.bold())
                        .foregroundStyle(.white)
                        .padding(.horizontal, 5)
                        .background(Capsule().fill(.red))
                }
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 6)
            // The window's pickers are segmented controls, so the tabs use an underline to look different from them.
            .overlay(alignment: .bottom) {
                Rectangle().fill(selected ? Color.accentColor : .clear).frame(height: 2)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}
