import AppKit
import SwiftUI
import WorkLogCore

@main
struct WorkLogApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        MenuBarExtra {
            MainWindow(model: delegate.model)
        } label: {
            MenuBarLabel(model: delegate.model)
        }
        .menuBarExtraStyle(.window)
    }
}

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = AppModel()

    func applicationDidFinishLaunching(_ notification: Notification) {
        // The bundle sets LSUIElement; `swift run` has no Info.plist, so the Dock icon is hidden here too.
        NSApp.setActivationPolicy(.accessory)
        model.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        model.stopRunForQuit()
    }
}

struct MenuBarLabel: View {
    @ObservedObject var model: AppModel

    var body: some View {
        let count = model.pendingSuggestions.count
        HStack(spacing: 2) {
            Image(nsImage: MenuBarIcon.image(mark: model.lastRunMark, strings: model.strings))
            if count > 0 { Text("\(count)") }
        }
    }
}

enum MenuBarIcon {
    private static let symbol = "book.closed"
    private static let dotDiameter: CGFloat = 6

    // The menu bar flattens template images to one color, so the mark is drawn into a non-template image.
    // The drawing handler runs at draw time, so labelColor follows the menu bar's light or dark appearance.
    static func image(mark: RunMark, strings: UIStrings) -> NSImage {
        let config = NSImage.SymbolConfiguration(pointSize: 14, weight: .regular)
        guard let base = NSImage(systemSymbolName: symbol, accessibilityDescription: "WorkLog")?.withSymbolConfiguration(config) else {
            return NSImage()
        }
        let dotColor: NSColor, description: String
        switch mark {
        case .none:
            base.isTemplate = true
            return base
        case .warning:
            (dotColor, description) = (.systemOrange, strings.menuBarWarning)
        case .failure:
            (dotColor, description) = (.systemRed, strings.menuBarFailure)
        }
        let size = NSSize(width: base.size.width + dotDiameter / 2, height: base.size.height)
        let image = NSImage(size: size, flipped: false) { rect in
            let glyph = NSRect(origin: .zero, size: base.size)
            base.draw(in: glyph)
            NSColor.labelColor.set()
            glyph.fill(using: .sourceAtop)
            dotColor.setFill()
            NSBezierPath(ovalIn: NSRect(x: rect.maxX - dotDiameter, y: rect.maxY - dotDiameter,
                                        width: dotDiameter, height: dotDiameter)).fill()
            return true
        }
        image.isTemplate = false
        image.accessibilityDescription = description
        return image
    }
}
