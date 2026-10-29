import SwiftUI
import WorkLogCore

@MainActor
enum Format {
    // Evidence dates are local "yyyy-MM-dd" strings, so they are shortened without a time zone round trip.
    static func evidenceDay(_ text: String) -> String {
        text.count == 10 ? text.dropFirst(5).replacingOccurrences(of: "-", with: "/") : text
    }

    static func provider(_ provider: AppSettings.Provider) -> String {
        provider == .claude ? "Claude" : "Codex"
    }

    static func clock(_ time: ClockTime) -> Date {
        Calendar.current.date(bySettingHour: time.hour, minute: time.minute, second: 0, of: Date()) ?? Date()
    }

    static func clockTime(_ date: Date) -> ClockTime {
        let parts = Calendar.current.dateComponents([.hour, .minute], from: date)
        return ClockTime(hour: parts.hour ?? 0, minute: parts.minute ?? 0)
    }
}

struct Muted: View {
    let text: String
    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text).font(.caption).foregroundStyle(.secondary)
    }
}

struct Card<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) { content }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(10)
            .background(RoundedRectangle(cornerRadius: 8).fill(Color(nsColor: .controlBackgroundColor)))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color(nsColor: .separatorColor)))
    }
}

struct Chip: View {
    let title: String
    let removeLabel: (String) -> String
    let onRemove: () -> Void

    var body: some View {
        HStack(spacing: 4) {
            Text(title).font(.caption).lineLimit(1).truncationMode(.head)
            Button(action: onRemove) { Image(systemName: "xmark").font(.system(size: 8, weight: .bold)) }
                .buttonStyle(.plain)
                .accessibilityLabel(removeLabel(title))
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 3)
        .background(Capsule().fill(Color(nsColor: .controlBackgroundColor)))
        .overlay(Capsule().stroke(Color(nsColor: .separatorColor)))
    }
}

// Lays chips out left to right and wraps; a grid would spread a few chips across the full width.
struct FlowLayout: Layout {
    var spacing: CGFloat = 6

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        arrange(subviews, width: proposal.width ?? .infinity).size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let (origins, _) = arrange(subviews, width: bounds.width)
        for (subview, origin) in zip(subviews, origins) {
            subview.place(at: CGPoint(x: bounds.minX + origin.x, y: bounds.minY + origin.y), proposal: .unspecified)
        }
    }

    private func arrange(_ subviews: Subviews, width: CGFloat) -> (origins: [CGPoint], size: CGSize) {
        var origins: [CGPoint] = []
        var x: CGFloat = 0, y: CGFloat = 0, rowHeight: CGFloat = 0, maxX: CGFloat = 0
        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > width {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            origins.append(CGPoint(x: x, y: y))
            x += size.width + spacing
            maxX = max(maxX, x - spacing)
            rowHeight = max(rowHeight, size.height)
        }
        return (origins, CGSize(width: maxX, height: y + rowHeight))
    }
}

struct Banner: View {
    let message: String
    let actionTitle: String
    let action: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.red)
            Text(message).font(.caption).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Button(actionTitle, action: action).controlSize(.small)
        }
        .padding(10)
        .background(Color.red.opacity(0.08))
    }
}

// 24-hour pickers match the HH:mm used everywhere else, whatever the system clock style is.
struct ClockPicker: View {
    let label: String
    @Binding var time: Date

    var body: some View {
        DatePicker(label, selection: $time, displayedComponents: .hourAndMinute)
            .environment(\.locale, Locale(identifier: "en_GB"))
    }
}
