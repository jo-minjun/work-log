import AppKit
import SwiftUI
import WorkLogCore

struct SettingsTab: View {
    @ObservedObject var model: AppModel
    @State private var addingTime = false
    @State private var newTime = Format.clock(ClockTime(hour: 12, minute: 0))
    @State private var addingQuiet = false
    @State private var quietStart = Format.clock(ClockTime(hour: 0, minute: 0))
    @State private var quietEnd = Format.clock(ClockTime(hour: 8, minute: 0))

    private var s: UIStrings { model.strings }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if model.settingsError != nil {
                Muted(s.settingsLocked)
            }
            Group {
                appLanguage
                logLanguage
                schedule
                quietHours
                provider
                logFolder
                sessionFolders
                HStack {
                    Text("Slack").bold()
                    Spacer()
                    Text(model.slackStatus).font(.caption).foregroundStyle(model.settings.slack?.userId == nil ? .secondary : .primary)
                }
                switchRow(s.launchAtLogin, model.binding(\.launchAtLogin))
                switchRow(s.notifyOnFinish, model.binding(\.notifyOnSuccess))
            }
            .disabled(model.settingsError != nil)
        }
        .controlSize(.small)
    }

    private var schedule: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(s.schedule).bold()
                Spacer()
                Picker("", selection: model.binding(\.schedule.mode)) {
                    Text(s.everyInterval).tag(AppSettings.Schedule.Mode.interval)
                    Text(s.atTimes).tag(AppSettings.Schedule.Mode.times)
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .fixedSize()
            }
            if model.settings.schedule.mode == .times {
                FlowLayout {
                    ForEach(model.settings.schedule.times, id: \.self) { time in
                        Chip(title: time.string, removeLabel: s.remove) { model.removeTime(time) }
                    }
                    addButton { addingTime = true }
                        .popover(isPresented: $addingTime) {
                            VStack(spacing: 8) {
                                ClockPicker(label: s.time, time: $newTime)
                                Button(s.add) {
                                    model.addTime(Format.clockTime(newTime))
                                    addingTime = false
                                }
                                .keyboardShortcut(.defaultAction)
                            }
                            .padding(12)
                        }
                }
            } else {
                Stepper(s.everyHours(model.settings.schedule.interval.hours),
                        value: model.binding(\.schedule.interval.hours), in: 1...24)
                ClockPicker(label: s.startingAt, time: Binding(
                    get: { Format.clock(model.settings.schedule.interval.anchor) },
                    set: { value in model.updateSettings { $0.schedule.interval.anchor = Format.clockTime(value) } }
                ))
            }
        }
    }

    private var quietHours: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(s.skipRunsDuring).bold()
            Muted(s.skipRunsNote)
            FlowLayout {
                ForEach(Array(model.settings.schedule.quietRanges.enumerated()), id: \.offset) { index, range in
                    Chip(title: "\(range.start.string)–\(range.end.string)", removeLabel: s.remove) { model.removeQuietRange(at: index) }
                }
                addButton { addingQuiet = true }
                    .popover(isPresented: $addingQuiet) {
                        VStack(alignment: .trailing, spacing: 8) {
                            ClockPicker(label: s.from, time: $quietStart)
                            ClockPicker(label: s.to, time: $quietEnd)
                            Button(s.add) {
                                model.addQuietRange(.init(start: Format.clockTime(quietStart), end: Format.clockTime(quietEnd)))
                                addingQuiet = false
                            }
                            .keyboardShortcut(.defaultAction)
                            // A range that starts and ends at the same minute would mean nothing, so it cannot be added.
                            .disabled(Format.clockTime(quietStart) == Format.clockTime(quietEnd))
                        }
                        .padding(12)
                    }
            }
        }
    }

    private var provider: some View {
        HStack {
            Text(s.provider).bold()
            Spacer()
            Picker("", selection: model.binding(\.provider)) {
                Text("Claude").tag(AppSettings.Provider.claude)
                Text("Codex").tag(AppSettings.Provider.codex)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .fixedSize()
            // A segmented picker cannot tag one segment, so the tag shows only while Codex is the choice.
            if model.settings.provider == .codex {
                Text(s.experimental)
                    .font(.system(size: 10))
                    .foregroundStyle(.orange)
                    .padding(.horizontal, 4)
                    .overlay(RoundedRectangle(cornerRadius: 4).stroke(.orange.opacity(0.6)))
            }
        }
    }

    private var logFolder: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(s.logFolder).bold()
            HStack {
                Text((model.settings.logFolder as NSString).expandingTildeInPath).font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.head)
                Spacer()
                Button(s.change) {
                    if let folder = FolderPicker.choose(multiple: false).first {
                        model.updateSettings { $0.logFolder = folder }
                    }
                }
            }
        }
    }

    private var sessionFolders: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Text(s.sessionFolders).bold()
                Muted(s.emptyMeansAll)
            }
            ForEach(model.settings.sessionFolders, id: \.self) { folder in
                Chip(title: folder, removeLabel: s.remove) { model.removeSessionFolder(folder) }
            }
            addButton { model.addSessionFolders(FolderPicker.choose(multiple: true)) }
        }
    }

    private var appLanguage: some View {
        HStack {
            Text(s.appLanguage).bold()
            Spacer()
            languagePicker(model.binding(\.appLanguage))
        }
    }

    private var logLanguage: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(s.logLanguage).bold()
                Spacer()
                languagePicker(model.binding(\.logLanguage))
            }
            Muted(s.logLanguageNote)
        }
    }

    // Each option is written in its own language so it can be found whichever language is active.
    private func switchRow(_ title: String, _ isOn: Binding<Bool>) -> some View {
        HStack {
            Text(title)
            Spacer()
            Toggle(title, isOn: isOn).toggleStyle(.switch).labelsHidden()
        }
    }

    private func languagePicker(_ selection: Binding<AppSettings.Language>) -> some View {
        Picker("", selection: selection) {
            Text("English").tag(AppSettings.Language.en)
            Text("한국어").tag(AppSettings.Language.ko)
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .fixedSize()
    }

    private func addButton(_ action: @escaping () -> Void) -> some View {
        Button(action: action) { Image(systemName: "plus").font(.caption) }
            .accessibilityLabel(s.add)
    }
}

enum FolderPicker {
    // Stored with "~" like the defaults, so settings.json stays portable and readable.
    static func choose(multiple: Bool) -> [String] {
        NSApp.activate(ignoringOtherApps: true)
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.canCreateDirectories = true
        panel.allowsMultipleSelection = multiple
        guard panel.runModal() == .OK else { return [] }
        return panel.urls.map { ($0.path as NSString).abbreviatingWithTildeInPath }
    }
}
