import SwiftUI
import WorkLogCore

struct StatusArea: View {
    @ObservedObject var model: AppModel

    var body: some View {
        let s = model.strings
        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(scheduleText).bold()
                Spacer()
                Toggle(s.scheduleSwitch, isOn: model.binding(\.scheduleEnabled))
                    .toggleStyle(.switch)
                    .labelsHidden()
                    .controlSize(.small)
                    .disabled(model.settingsError != nil)
                    .help(model.settings.scheduleEnabled ? s.stopSchedule : s.startSchedule)
                Button(model.isRunning ? s.running : s.runNow) { model.runNow() }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                    .disabled(model.isRunning)
            }
            if let run = model.lastRun {
                HStack(spacing: 4) {
                    Muted(s.lastRun(DisplayText.time(run.startedAt, now: model.now, strings: s)))
                    Text(run.result == .failed ? s.failed : run.hasWarnings ? s.succeededWithWarnings : s.succeeded)
                        .font(.caption)
                        .foregroundStyle(run.result == .failed ? .red : run.hasWarnings ? .orange : .green)
                    Muted("· \(Format.provider(run.provider))")
                }
                if run.result == .failed, let reason = run.reason { Muted(reason) }
            }
        }
        .padding(12)
    }

    private var scheduleText: String {
        let s = model.strings
        guard model.settings.scheduleEnabled else { return s.scheduleOff }
        return model.nextRun.map { DisplayText.nextRun($0, now: model.now, strings: s) } ?? s.noRunScheduled
    }
}
