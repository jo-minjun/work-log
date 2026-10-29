import Foundation

// One stored property per user-visible string, so the compiler rejects a language that misses one.
// Strings that take values are closures. Collector data (run reasons, provider names, paths) is not translated.
public struct UIStrings {
    public let locale: Locale

    // Window
    public let tabSuggestions: String
    public let tabHistory: String
    public let tabSettings: String
    public let quit: String
    public let cancel: String
    public let dismiss: String
    public let backUpAndReset: String
    public let quitAlertTitle: String
    public let quitAlertBody: String

    // Status area
    public let scheduleOff: String
    public let noRunScheduled: String
    public let nextRun: (String) -> String
    public let runNow: String
    public let running: String
    public let scheduleSwitch: String
    public let startSchedule: String
    public let stopSchedule: String
    public let lastRun: (String) -> String
    public let succeeded: String
    public let succeededWithWarnings: String
    public let failed: String
    public let skipped: String

    // Usage area
    public let tokensLabel: String
    public let noUsageData: String
    public let unavailable: String
    public let session: String
    public let weekly: String
    public let usage: (String) -> String
    public let percentUsed: (Int) -> String
    public let tokenCount: (String) -> String
    public let runCount: (Int) -> String
    public let thisMonth: (String) -> String
    public let withoutCostData: (Int) -> String
    public let minutesAgo: (Int) -> String
    public let hoursAgo: (Int) -> String
    public let daysAgo: (Int) -> String
    public let resetPassed: String
    public let resetsInDays: (Int, Int) -> String
    public let resetsInHours: (Int, Int) -> String
    public let resetsInMinutes: (Int) -> String

    // Suggestions
    public let answersApplyNext: String
    public let noSuggestions: String
    public let newProject: (String) -> String
    public let evidenceCounts: (_ days: Int, _ items: Int) -> String
    public let moreEvidence: (Int) -> String
    public let description: String
    public let add: String
    public let reject: String
    public let neverSuggest: String

    // History
    public let runs: String
    public let noRuns: String
    public let suggestionsAndAnswers: String
    public let noAnswers: String
    public let answeredOn: (String) -> String
    public let answerAdded: String
    public let answerRejected: String
    public let waitingForNextCollection: (String) -> String
    public let appliedAt: (String) -> String

    // Settings
    public let settingsLocked: String
    public let schedule: String
    public let everyInterval: String
    public let atTimes: String
    public let time: String
    public let everyHours: (Int) -> String
    public let startingAt: String
    public let skipRunsDuring: String
    public let skipRunsNote: String
    public let from: String
    public let to: String
    public let provider: String
    public let experimental: String
    public let logFolder: String
    public let change: String
    public let sessionFolders: String
    public let emptyMeansAll: String
    public let launchAtLogin: String
    public let notifyOnFinish: String
    public let appLanguage: String
    public let logLanguage: String
    public let logLanguageNote: String
    public let remove: (String) -> String
    public let slackNotChecked: String
    public let slackChecked: (_ who: String, _ relativeTime: String) -> String

    // Errors and banners
    public let settingsUnreadable: (String) -> String
    public let suggestionsUnreadable: (String) -> String
    public let couldNotBackUp: (_ file: String, _ detail: String) -> String
    public let couldNotSaveSettings: (String) -> String
    public let couldNotSaveAnswer: (String) -> String

    // Notifications
    public let collectionFailed: String
    public let collectionFinished: String
    public let collectionFinishedWithWarnings: String
    public let endedWithoutRecord: (Int32) -> String
    public let newSuggestions: (Int) -> String

    // Menu bar icon
    public let menuBarWarning: String
    public let menuBarFailure: String

    public static func `for`(_ language: AppSettings.Language) -> UIStrings {
        switch language {
        case .en: return en
        case .ko: return ko
        }
    }

    public static let en = UIStrings(
        locale: Locale(identifier: "en_US"),
        tabSuggestions: "Suggestions",
        tabHistory: "History",
        tabSettings: "Settings",
        quit: "Quit",
        cancel: "Cancel",
        dismiss: "Dismiss",
        backUpAndReset: "Back up and reset",
        quitAlertTitle: "A collection is running",
        quitAlertBody: "Quitting stops it, and the run is recorded as stopped.",
        scheduleOff: "Schedule off",
        noRunScheduled: "No run scheduled",
        nextRun: { "Next run \($0)" },
        runNow: "Run now",
        running: "Running…",
        scheduleSwitch: "Schedule",
        startSchedule: "Start the schedule",
        stopSchedule: "Stop the schedule",
        lastRun: { "Last run \($0)" },
        succeeded: "Succeeded",
        succeededWithWarnings: "Succeeded with warnings",
        failed: "Failed",
        skipped: "Skipped",
        tokensLabel: "Tokens",
        noUsageData: "No usage data",
        unavailable: "Unavailable",
        session: "Session",
        weekly: "Weekly",
        usage: { "\($0) usage" },
        percentUsed: { "\($0)% used" },
        tokenCount: { "\($0) tokens" },
        runCount: { $0 == 1 ? "1 run" : "\($0) runs" },
        thisMonth: { "This month: \($0)" },
        withoutCostData: { "(+\($0) without cost data)" },
        minutesAgo: { "updated \($0) min ago" },
        hoursAgo: { "updated \($0) h ago" },
        daysAgo: { "updated \($0) d ago" },
        resetPassed: "Reset passed",
        resetsInDays: { "Resets in \($0)d \($1)h" },
        resetsInHours: { "Resets in \($0)h \($1)m" },
        resetsInMinutes: { "Resets in \($0)m" },
        answersApplyNext: "Answers apply on the next collection",
        noSuggestions: "No suggestions",
        newProject: { "New project: \($0)" },
        evidenceCounts: { days, items in "\(days) \(days == 1 ? "day" : "days"), \(items) \(items == 1 ? "item" : "items")" },
        moreEvidence: { "+\($0) more" },
        description: "Description",
        add: "Add",
        reject: "Reject",
        neverSuggest: "Never suggest",
        runs: "Runs",
        noRuns: "No runs yet",
        suggestionsAndAnswers: "Suggestions and answers",
        noAnswers: "No answers yet",
        answeredOn: { "answered \($0)" },
        answerAdded: "Added",
        answerRejected: "Rejected",
        waitingForNextCollection: { "\($0) → waiting for the next collection" },
        appliedAt: { " → applied \($0)" },
        settingsLocked: "Settings can be changed again after settings.json is backed up and reset.",
        schedule: "Schedule",
        everyInterval: "Every interval",
        atTimes: "At times",
        time: "Time",
        everyHours: { "Every \($0) h" },
        startingAt: "Starting at",
        skipRunsDuring: "Skip runs during",
        skipRunsNote: "Scheduled runs in these hours are skipped. Run now still works.",
        from: "From",
        to: "To",
        provider: "Provider",
        experimental: "Experimental",
        logFolder: "Log folder",
        change: "Change",
        sessionFolders: "Session folders",
        emptyMeansAll: "(empty means all)",
        launchAtLogin: "Launch at login",
        notifyOnFinish: "Notify when a collection finishes",
        appLanguage: "App language",
        logLanguage: "Log language",
        logLanguageNote: "Switching starts a new month file.",
        remove: { "Remove \($0)" },
        slackNotChecked: "Checked on next collection",
        slackChecked: { who, relativeTime in "\(who) · checked \(relativeTime)" },
        settingsUnreadable: { "settings.json could not be read: \($0)" },
        suggestionsUnreadable: { "suggestions.json could not be read: \($0)" },
        couldNotBackUp: { file, detail in "Could not back up \(file): \(detail)" },
        couldNotSaveSettings: { "Could not save settings: \($0)" },
        couldNotSaveAnswer: { "Could not save the answer: \($0)" },
        collectionFailed: "Collection failed",
        collectionFinished: "Collection finished",
        collectionFinishedWithWarnings: "Collection finished with warnings",
        endedWithoutRecord: { "run.sh exited with code \($0) without recording the run" },
        newSuggestions: { $0 == 1 ? "1 new suggestion" : "\($0) new suggestions" },
        menuBarWarning: "WorkLog, last run had warnings",
        menuBarFailure: "WorkLog, last run failed"
    )

    public static let ko = UIStrings(
        locale: Locale(identifier: "ko_KR"),
        tabSuggestions: "제안",
        tabHistory: "기록",
        tabSettings: "설정",
        quit: "종료",
        cancel: "취소",
        dismiss: "닫기",
        backUpAndReset: "백업 후 초기화",
        quitAlertTitle: "수집이 실행 중입니다",
        quitAlertBody: "종료하면 수집이 멈추고, 이 실행은 '중단됨'으로 기록됩니다.",
        scheduleOff: "일정 꺼짐",
        noRunScheduled: "예정된 실행 없음",
        nextRun: { "다음 실행 \($0)" },
        runNow: "지금 실행",
        running: "실행 중…",
        scheduleSwitch: "일정",
        startSchedule: "일정 시작",
        stopSchedule: "일정 중지",
        lastRun: { "마지막 실행 \($0)" },
        succeeded: "성공",
        succeededWithWarnings: "경고와 함께 성공",
        failed: "실패",
        skipped: "건너뜀",
        tokensLabel: "토큰",
        noUsageData: "사용량 데이터 없음",
        unavailable: "확인 불가",
        session: "세션",
        weekly: "주간",
        usage: { "\($0) 사용량" },
        percentUsed: { "\($0)% 사용" },
        tokenCount: { "\($0) 토큰" },
        runCount: { "\($0)회 실행" },
        thisMonth: { "이번 달: \($0)" },
        withoutCostData: { "(비용 정보 없는 실행 +\($0)회)" },
        minutesAgo: { "\($0)분 전 갱신" },
        hoursAgo: { "\($0)시간 전 갱신" },
        daysAgo: { "\($0)일 전 갱신" },
        resetPassed: "초기화 시각 지남",
        resetsInDays: { "초기화까지 \($0)일 \($1)시간" },
        resetsInHours: { "초기화까지 \($0)시간 \($1)분" },
        resetsInMinutes: { "초기화까지 \($0)분" },
        answersApplyNext: "답은 다음 수집 때 반영됩니다",
        noSuggestions: "제안 없음",
        newProject: { "새 프로젝트 후보: \($0)" },
        evidenceCounts: { days, items in "\(days)일 \(items)건" },
        moreEvidence: { "외 \($0)건" },
        description: "설명",
        add: "추가",
        reject: "거절",
        neverSuggest: "다시 추천 안 함",
        runs: "실행 기록",
        noRuns: "실행 기록 없음",
        suggestionsAndAnswers: "제안과 답",
        noAnswers: "답한 제안 없음",
        answeredOn: { "\($0)에 답함" },
        answerAdded: "추가",
        answerRejected: "거절",
        waitingForNextCollection: { "\($0) → 다음 수집 때 반영 예정" },
        appliedAt: { " → \($0) 반영됨" },
        settingsLocked: "settings.json을 백업하고 초기화하면 설정을 다시 변경할 수 있습니다.",
        schedule: "실행 일정",
        everyInterval: "주기마다",
        atTimes: "시각마다",
        time: "시각",
        everyHours: { "\($0)시간마다" },
        startingAt: "기준 시각",
        skipRunsDuring: "실행 건너뛸 시간",
        skipRunsNote: "이 시간대의 예약 실행은 건너뜁니다. 지금 실행은 그대로 동작합니다.",
        from: "시작",
        to: "끝",
        provider: "실행 도구",
        experimental: "실험적",
        logFolder: "업무 로그 저장 폴더",
        change: "변경",
        sessionFolders: "수집할 세션 폴더",
        emptyMeansAll: "(비우면 전체)",
        launchAtLogin: "로그인 시 자동 실행",
        notifyOnFinish: "수집이 끝나면 알림",
        appLanguage: "앱 언어",
        logLanguage: "로그 언어",
        logLanguageNote: "언어를 바꾸면 새 월별 파일에 기록됩니다.",
        remove: { "\($0) 삭제" },
        slackNotChecked: "다음 수집 때 확인",
        slackChecked: { who, relativeTime in "\(who) · \(relativeTime) 확인" },
        settingsUnreadable: { "settings.json을 읽을 수 없습니다: \($0)" },
        suggestionsUnreadable: { "suggestions.json을 읽을 수 없습니다: \($0)" },
        couldNotBackUp: { file, detail in "백업할 수 없습니다 (\(file)): \(detail)" },
        couldNotSaveSettings: { "설정을 저장할 수 없습니다: \($0)" },
        couldNotSaveAnswer: { "답을 저장할 수 없습니다: \($0)" },
        collectionFailed: "수집 실패",
        collectionFinished: "수집 완료",
        collectionFinishedWithWarnings: "경고와 함께 수집 완료",
        endedWithoutRecord: { "run.sh가 실행을 기록하지 못하고 종료되었습니다 (종료 코드 \($0))" },
        newSuggestions: { "새 제안 \($0)건" },
        menuBarWarning: "WorkLog, 마지막 실행에 경고가 있습니다",
        menuBarFailure: "WorkLog, 마지막 실행이 실패했습니다"
    )
}
