# work-log

[English](README.md) | 한국어

work-log는 매일 한 일을 기록합니다. 헤드리스 코딩 에이전트(Claude Code 또는 Codex)가 정해진 시각에 `work-log` 스킬을 실행합니다. 스킬이 모으는 것은 다음과 같습니다.

- Claude Code 세션
- 내가 보낸 Slack 메시지와 DM
- 내가 참여한 스레드에서 나온 결정과, 아직 확인을 기다리는 합의

모은 내용은 날짜와 프로젝트별로 월별 Markdown 로그에 씁니다. 이 로그는 데일리 스탠드업과 성과 평가의 근거 자료로 씁니다.

저장소는 두 부분으로 되어 있습니다.

- **WorkLog.app**: macOS 메뉴 막대 앱입니다. 실행 일정을 관리하고, 지금 실행 버튼을 제공하고, 실행 기록과 사용량을 보여 줍니다. 새 프로젝트 제안에 대한 답도 여기서 받습니다.
- **`skill/work-log`**: 스킬과 Python 스크립트입니다. 스킬을 직접 실행할 수도 있습니다(Claude Code에서는 `/work-log`, Codex에서는 `$work-log`).

<p align="center">
  <img src="docs/images/suggestions.png" width="260" alt="Suggestions tab">
  <img src="docs/images/history.png" width="260" alt="History tab">
  <img src="docs/images/settings.png" width="260" alt="Settings tab">
</p>

<p align="center"><sub>Suggestions(제안), History(기록), Settings(설정) 탭입니다. 스크린샷은 예시 데이터로 찍었습니다.</sub></p>

## 화면 이름

앱의 기본 화면 언어는 영어입니다. 이 문서는 영어 화면 이름을 쓰고, 한국어 화면 이름을 괄호 안에 적습니다. 화면 언어는 설정 탭의 **App language**(앱 언어)에서 바꿉니다.

## 요구 사항

- macOS 14 이상
- Command Line Tools(`xcode-select --install`)와 Swift 5.10 이상. Xcode는 필요하지 않습니다.
- **Python 3.11 이상이 `python3`로 실행되어야 합니다.** Command Line Tools에 들어 있는 `python3`는 3.9라서 부족합니다. Homebrew나 mise 등으로 새 버전을 설치하세요. 스크립트는 표준 라이브러리만 씁니다.
- 로그인된 Claude Code(`claude`) 또는 Codex(`codex`). Codex 지원은 실험 단계입니다([Codex](#codex-실험적) 참고).
- Claude로 Slack을 수집하려면 Claude Code용 Slack 플러그인이 필요합니다. Slack이 없으면 세션만 수집하고, 실행은 경고와 함께 끝납니다.

## 설치

```sh
git clone https://github.com/jo-minjun/work-log.git
cd work-log
./install.sh
```

`install.sh`는 다음 일을 합니다.

1. 실행 PATH의 `python3`가 3.11 이상인지 확인합니다. 아니면 멈춥니다.
2. 셸에서 `python3`, `claude`, `codex`가 있는 폴더를 기록합니다. 앱은 로그인 셸 없이 실행을 시작하므로 이 폴더 정보가 필요합니다.
3. 앱을 release 모드로 빌드하고 ad hoc 서명한 뒤 `~/Applications/WorkLog.app`으로 설치합니다.
4. 두 에이전트의 사용자 스킬 폴더에 스킬 링크를 만듭니다. 두 링크 모두 `<저장소>/skill/work-log`를 직접 가리킵니다.
   - Claude Code용: `~/.claude/skills/work-log`
   - Codex용: `~/.agents/skills/work-log`

   이미 저장소를 가리키는 링크는 그대로 둡니다. 다른 곳을 가리키는 링크는 바꾸고, 이전 대상을 출력합니다. 두 위치 중 한 곳에 실제 파일이나 폴더가 있으면, 아무것도 바꾸기 전에 설치를 멈춥니다.
5. 앱을 엽니다.

옵션:

| 옵션 | 효과 |
|---|---|
| `--prefix DIR` | 앱을 `~/Applications` 대신 `DIR`에 설치합니다 |
| `--no-open` | 설치한 뒤 앱을 열지 않습니다 |

`install.sh`를 다시 실행하면 그 자리에서 업그레이드합니다. WorkLog가 실행 중이면 설치 스크립트가 앱에 종료를 요청합니다. 수집이 진행 중이면 아무것도 바꾸지 않고 멈춥니다. `python3`, `claude`, `codex`의 위치를 옮겼다면 다시 실행하세요.

저장소를 클론한 위치에 그대로 두세요. 앱은 클론한 저장소에서 스킬을 실행합니다. Claude를 쓸 때는 스킬 경로에 공백이 있으면 안 됩니다.

## 첫 실행

- **메뉴 막대.** WorkLog는 Dock 아이콘이 없습니다. 메뉴 막대 아이콘을 눌러 창을 엽니다.
- **로그인 항목.** 처음 실행할 때 앱은 로그인 시 열리도록 자신을 등록합니다. 이때 macOS가 "로그인 항목 추가됨" 알림을 보여 줄 수 있습니다. 설정의 **Launch at login**(로그인 시 자동 실행)이나 시스템 설정 → 일반 → 로그인 항목에서 끌 수 있습니다.
- **일정 꺼짐.** 새로 설치하면 일정이 꺼진 상태로 시작합니다. 창은 설정 탭으로 열립니다. 설정을 확인한 뒤, 창 맨 위 **Run now**(지금 실행) 옆의 일정 스위치를 켜세요. 같은 스위치로 다시 끌 수 있습니다. 일정이 꺼져 있어도 **Run now**는 동작합니다.
- **로그 폴더.** 기본값은 `~/WorkLog`입니다. 첫 실행 때 소유자만 접근할 수 있게 만들어집니다. 직접 고른 폴더는 미리 있어야 합니다. 에이전트가 로그 폴더 안의 파일을 바꿀 수 있으므로, WorkLog는 홈 폴더, `/`, 그리고 데이터 폴더를 포함하는 폴더를 거부합니다.
- **폴더 접근 확인.** 로그 폴더가 iCloud Drive, 문서, 데스크탑 안에 있으면 macOS가 WorkLog의 접근을 허용할지 묻습니다. 첫 실행은 답을 최대 120초 기다립니다. 앱은 ad hoc 서명이라 다시 빌드할 때마다 서명이 바뀝니다. 그래서 다시 설치한 뒤에 macOS가 또 물을 수 있습니다.
- **Slack 사용자.** 첫 실행 때 Slack 도구에 내가 누구인지 묻고, 사용자 ID와 표시 이름만 저장합니다. 결과는 설정 탭에 보입니다.

## 설정

| 설정 | 기본값 | 설명 |
|---|---|---|
| Schedule(실행 일정) | At times(시각마다): 10:00, 22:00 | **At times**는 매일 목록의 시각에 실행합니다. **Every interval**(주기마다)은 기준 시각부터 1–24시간마다 실행하고(기본 08:00부터 4시간), 매일 기준 시각에서 다시 시작합니다 |
| Skip runs during(실행 건너뛸 시간) | 없음 | 범위 안에 든 예약 실행은 건너뜁니다. Run now는 그대로 동작합니다. 시작 시각은 포함하고 끝 시각은 포함하지 않습니다. 범위가 자정을 넘어도 됩니다 |
| Provider(실행 도구) | Claude | Claude 또는 Codex(Experimental, 실험적) |
| Log folder(업무 로그 저장 폴더) | `~/WorkLog` | [첫 실행](#첫-실행) 참고 |
| Session folders(수집할 세션 폴더) | 비어 있음(모든 세션) | 작업 디렉터리가 이 폴더 아래에 있는 세션만 수집합니다 |
| App language(앱 언어) | English | 앱 화면의 언어입니다. 로그 언어와 따로 정합니다 |
| Log language(로그 언어) | English | 영어 또는 한국어. [로그 언어](#로그-언어) 참고 |
| Launch at login(로그인 시 자동 실행) | 켜짐 | |
| Notify when a collection finishes(수집이 끝나면 알림) | 켜짐 | 실패와 새 제안은 이 설정과 상관없이 항상 알립니다 |

설정은 데이터 폴더의 `settings.json`에 저장됩니다. 일정과 앱 관련 키는 앱이 관리합니다. 수집기는 `slack` 항목만 씁니다.

## 한 번의 실행이 하는 일

1. 앱에서 답한 제안을 반영합니다.
2. Slack 사용자를 확인합니다.
3. 수집할 날을 하루씩 수집합니다. 기본 범위는 마지막으로 완료한 날의 다음 날부터 오늘까지입니다. 각 날의 섹션은 처음부터 다시 만듭니다.
4. 기본 프로젝트(`Other`, 한국어 로그에서는 `기타`)에 남은 항목을 주제별로 묶고, 새 프로젝트를 제안합니다([제안](#제안) 참고).

프로젝트 안에서 각 날짜는 하위 섹션 네 개로 나뉩니다. Claude 세션, Slack, 결정, 확인 필요입니다. 확인 필요에는 아직 누군가의 확인을 기다리는 합의가 들어갑니다.

실행 한 번은 기록에 한 줄로 남습니다. 결과는 성공, 경고와 함께 성공, 실패, 건너뜀 중 하나입니다. 실패하는 경우의 예는 다음과 같습니다.
- 에이전트가 실행 동안 아무것도 쓰지 않았을 때
- 30분 제한 시간을 넘겼을 때
- 로그 폴더를 읽을 수 없을 때

실행은 겹치지 않습니다. 실행 중에 돌아온 예약 시각은 건너뜁니다.

특정 날짜를 직접 수집하려면 새 세션에서 스킬을 실행하세요.

```
/work-log                          # 수집할 날 전부 (Codex: $work-log)
/work-log 2026-10-22               # 하루
/work-log 2026-10-20..2026-10-26   # 범위, 양 끝 포함
```

스킬을 실행한 세션은 수집 대상에서 빠집니다. 그러므로 작업하던 세션이 아니라 새 세션에서 실행하세요.

## 로그 언어

| 항목 | 영어 | 한국어 |
|---|---|---|
| 월별 파일 | `2026-10 Work Log.md` | `2026년 10월 업무 로그.md` |
| 프로젝트 목록 파일 | `Active Projects.md` | `진행 중인 프로젝트.md` |
| 날짜 제목 | `## 2026-10-29 (Thu)` | `## 2026-10-29 (목)` |
| 기본 프로젝트 | `Other` | `기타` |

로그 폴더의 프로젝트 목록 파일에는 프로젝트마다 `## <이름>` 섹션과 짧은 설명이 있습니다. 에이전트는 이 설명을 보고 항목을 분류합니다. 이 파일은 언제든 고쳐도 됩니다.

언어를 바꿔도 기존 파일은 변환하지 않습니다. 파일 이름이 달라서, 새 언어의 내용은 새 월별 파일에 기록됩니다. 새 언어의 프로젝트 목록이 없으면 지금 목록을 복사합니다. 바꾸기 전과 후에 모두 수집된 날은 두 파일에 모두 나타납니다. 예를 들어 오늘은 실행할 때마다 다시 수집되므로 두 파일에 다 들어갑니다. 이런 날의 중복은 정리하지 않습니다.

## 제안

관련된 일이 계속 `Other`에 쌓이면, 실행이 새 프로젝트를 제안합니다. 한 주제가 제안 대상이 되려면 서로 다른 날 2일 이상에 걸쳐 근거가 있고, 항목이 3개 이상이어야 합니다. 근거를 보는 기간은 이번 달 1일의 15일 전부터입니다. 대기 중인 제안은 Suggestions(제안) 탭에 근거와 고칠 수 있는 설명 초안과 함께 나옵니다.

| 버튼 | 효과 |
|---|---|
| **Add**(추가) | 다음 실행이 입력한 설명으로 프로젝트 목록에 프로젝트를 추가하고, 맞는 항목을 `Other`에서 옮깁니다. 날짜를 다시 수집하지 않고 옮깁니다 |
| **Reject**(거절) | 거절이 기록됩니다. 거절한 날 이후의 새 근거가 있을 때만 그 주제가 다시 제안됩니다 |
| **Never suggest**(다시 추천 안 함) | 그 주제는 다시 제안하지 않습니다. History(기록) 탭의 스위치로 되돌릴 수 있습니다 |

주제가 이미 있는 프로젝트에 맞으면, 실행은 묻지 않고 그 프로젝트의 설명을 넓히고 항목을 옮깁니다.

## 사용량 표시

사용량 영역은 두 가지 보기를 오갑니다.

- **`$`**(Claude) 또는 **Tokens**(토큰, Codex): 이번 달 실행 횟수와 비용 또는 토큰입니다. 실행 기록에서 계산합니다. 비용을 보고하지 않은 Claude 실행은 `(+n without cost data)`로 표시합니다.
- **`%`**: 5시간 한도와 주간 한도, 초기화 시각, "n분 전 갱신"을 보여 줍니다.
  - Codex: `~/.codex/sessions`의 가장 새 파일에서 읽습니다. 이 형식은 공개 API가 아니라서 "Unavailable"(확인 불가)로 보일 수 있습니다.
  - Claude: Claude Code는 한도 정보를 상태 줄 명령에만 넘겨 줍니다. 아래의 연결 코드를 추가하세요.

### 상태 줄 연결

`skill/work-log/scripts/save_rate_limits.sh`는 표준 입력으로 받은 상태 줄 JSON에서 `rate_limits`를 읽어 `claude-rate-limits.json`에 저장합니다. 아무것도 출력하지 않고 항상 0으로 끝나므로, 상태 줄을 바꾸거나 깨뜨리지 않습니다. 기존 상태 줄 명령에서, 입력을 쓰기 전에 이 스크립트를 호출하세요.

```sh
#!/bin/sh
input=$(cat)
# WorkLog: 사용량 저장 (출력 없음, 항상 0으로 끝남)
printf '%s' "$input" | ~/.claude/skills/work-log/scripts/save_rate_limits.sh

# ...기존 상태 줄 코드. 표준 입력 대신 "$input"을 읽게 하세요...
```

아직 상태 줄이 없으면, 위 스크립트에 출력 줄을 넣어 저장하고 `~/.claude/settings.json`에서 그 파일을 가리키세요.

```json
{ "statusLine": { "type": "command", "command": "~/.claude/statusline.sh" } }
```

이 값은 대화형 Claude Code 세션이 열려 있을 때만 갱신됩니다. 그래서 화면에는 값이 얼마나 오래됐는지가 함께 나옵니다.

## 데이터와 로그

| 위치 | 내용 |
|---|---|
| `~/Library/Application Support/WorkLog/` | `settings.json`, `suggestions.json`(과 `.lock`), `runs.jsonl`(실행 기록), `state.json`(마지막 완료일), `claude-rate-limits.json` |
| `~/Library/Logs/work-log/` | `run.log`와 `app-runner.log`(텍스트 로그), 실행마다 `<날짜-시각>.json`(대화 기록을 포함한 에이전트 출력)과 `.err`, 실행 중에만 있는 `.lock` |
| 로그 폴더(기본 `~/WorkLog`) | 월별 파일과 프로젝트 목록 |

WorkLog의 두 폴더는 소유자만 접근할 수 있고(0700), 그 안의 파일은 0600입니다. 실행마다 생기는 `.json`과 `.err` 파일은 7일 뒤에 지웁니다. `run.log`와 `app-runner.log`가 1MB를 넘으면 마지막 1000줄만 남깁니다. 각 실행은 새 임시 폴더에서 작업하고, 실행이 끝나거나 중지되면 그 폴더를 지웁니다.

## 환경 변수

| 변수 | 효과 |
|---|---|
| `WORKLOG_HOME` | 데이터 폴더를 바꿉니다 |
| `WORKLOG_LOG_DIR` | 로그 폴더를 바꿉니다 |
| `WORKLOG_EXTRA_PATH` | 기본 실행 PATH 앞에 폴더를 추가합니다. `install.sh`가 앱의 Info.plist(`WorkLogExtraPath`)에 씁니다 |
| `WORKLOG_PATH` | 실행 PATH 전체를 바꿉니다. 테스트용입니다 |

기본 실행 PATH는 `~/.local/share/mise/shims:~/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin`입니다. 앱, `run.sh`, Python 스크립트는 모두 `WORKLOG_HOME`과 `WORKLOG_LOG_DIR`을 읽습니다. 주로 개발과 테스트에서, 테스트가 실제 데이터를 건드리지 않게 하려고 씁니다.

## Codex (실험적)

Codex는 새 임시 폴더에서 `codex exec --json --sandbox workspace-write`로 실행합니다. 로그 폴더와 WorkLog 데이터 폴더에 쓸 수 있습니다. 알려진 제한은 다음과 같습니다.

- **Slack 호출이 취소될 수 있습니다.** 헤드리스 Codex는 승인이 필요한 MCP 도구 호출을 취소할 수 있습니다([openai/codex#24135](https://github.com/openai/codex/issues/24135)). `~/.codex/config.toml`에서 Slack 플러그인의 `default_tools_approval_mode`를 설정하면 이 문제를 줄일 수 있습니다. 꼭 필요한 것만 승인하세요. Slack 설정에 맞는 정확한 표 이름은 Codex 설정 문서를 참고하세요.
- **MCP 제한이 없습니다.** WorkLog에는 Codex용 허용 목록이 없습니다. Codex 실행은 Codex에 설정한 모든 MCP 도구를 부를 수 있습니다. 여기에는 메시지를 보내는 Slack 도구도 포함됩니다.
- **세션이 남습니다.** Codex는 세션 파일(대화 원문)을 `~/.codex/sessions`에 계속 보관합니다. WorkLog는 그 파일에서 사용량을 읽기 때문에 `--ephemeral`을 넘기지 않습니다.
- **Codex는 비용을 보고하지 않고** 토큰만 보고합니다.

**Slack을 쓸 수 없을 때**(두 실행 도구 모두 해당), 실행은 수집할 첫날 하나만, 세션만으로 경고와 함께 쓰고 멈춥니다. 그날은 완료로 처리됩니다. 그래서 Slack 문제가 계속되면 실행할 때마다 밀린 날이 하루씩만 줄어듭니다. 이런 실행은 경고와 함께 성공으로 기록되고, 메뉴 막대에 주황색 점이 표시됩니다. Slack 접근을 고친 뒤, 해당 날짜를 직접 다시 수집하세요.

## 보안 모델과 남은 위험

- **헤드리스 Claude 권한.** Claude는 `--permission-mode dontAsk`로 실행합니다. 이 모드는 허용 목록에 없는 도구 호출을 모두 거부합니다. 허용 목록은 다음과 같습니다.
  - 수집 스크립트 다섯 개를 절대 경로로 실행하는 `python3 <skill>/scripts/<name>.py`
  - `Read`
  - 로그 폴더와 실행의 임시 폴더 안에서만 `Edit`
  - `work-log` 스킬
  - 읽기 전용 Slack 도구 세 개: 검색, 스레드 읽기, 프로필 읽기
- **내 Claude Code 설정도 함께 적용됩니다.** `~/.claude/settings.json`의 허용 규칙, 훅, 플러그인, MCP 서버가 합쳐집니다. `dontAsk`는 아무 규칙도 허용하지 않은 것만 거부합니다.
- **`Read`는 범위 제한이 없습니다.** Slack 메시지에 심어진 문구가 에이전트에게 로컬 파일을 읽게 할 수 있습니다. 밖으로 나가는 길은 좁습니다. 웹 접근이 없고, 다른 셸 명령이 없고, 두 폴더 밖에는 쓸 수 없고, Slack은 읽기 전용입니다. 그래도 에이전트가 읽은 내용이 로그 폴더(iCloud가 동기화할 수 있음)나, 7일 동안 남는 실행의 `.json` 대화 기록에 들어갈 수 있습니다.
- **프롬프트 인젝션.** 스킬은 수집한 모든 글(Slack 메시지, 세션 프롬프트, 프로젝트 목록)을 데이터로 다룹니다. 그 안의 지시, 명령, URL은 따르지 않습니다.
- **비밀 값 검사.** `write_day.py day`와 `suggestions.py propose`는 인증 정보처럼 보이는 값을 거부하고 종료 코드 4로 끝납니다. 예를 들면 Slack·GitHub 토큰, AWS 키, `sk-` 키, JWT, 개인 키, 그리고 signature·token·key·password 쿼리 값이 있는 URL입니다. 패턴 기반이라 모든 비밀 값을 잡지는 못합니다.
- **경로 옵션.** 허용된 스크립트는 `--settings`, `--state`, `--file` 경로 옵션을 받습니다. 에이전트가 이 옵션으로 쓰기 가능한 다른 폴더에 정해진 이름의 파일(`settings.json`, `state.json` 등)을 만들 수 있습니다. 내용은 에이전트가 고른 것이 아니라 WorkLog 자신의 데이터이므로 위험은 낮습니다.

## 잠자기와 놓친 실행

WorkLog는 Mac이 깨어 있고 로그인한 동안에만 실행합니다. 잠자기 중에 지나간 예약 시각(타이머가 2분 넘게 늦게 울린 경우)은 건너뜀으로 기록하고, 따라잡지 않습니다. 한 번의 잠자기에서 여러 시각을 놓쳐도 기록은 하나만 남습니다. 따라잡으려면 **Run now**(지금 실행)를 누르세요. 기본 실행은 마지막 완료일 이후의 모든 날을 수집합니다.

## 개발

```sh
cd skill/work-log && python3 -m unittest discover -s tests   # Python 테스트
cd app && swift run WorkLogChecks                            # Swift 검사
cd app && WORKLOG_SKILL_PATH="$PWD/../skill/work-log" swift run WorkLog   # 번들 없이 앱 실행
```

`swift run WorkLog`는 스킬 경로와 `WORKLOG_EXTRA_PATH`를 Info.plist 대신 환경 변수에서 읽습니다. 실제 데이터를 건드리지 않으려면 `WORKLOG_HOME`과 `WORKLOG_LOG_DIR`을 지정하세요.

## 삭제

1. 창에서 WorkLog를 종료합니다. 실행 중이면 앱이 먼저 묻습니다.
2. 시스템 설정 → 일반 → 로그인 항목에서 지웁니다. 또는 종료하기 전에 **Launch at login**(로그인 시 자동 실행)을 끕니다.
3. 앱과 스킬 링크 두 개를 지웁니다.
   ```sh
   rm -rf ~/Applications/WorkLog.app      # 또는 <prefix>/WorkLog.app
   rm ~/.claude/skills/work-log ~/.agents/skills/work-log
   ```
4. 데이터 폴더와 로그 폴더를 지웁니다.
   ```sh
   rm -rf ~/Library/Application\ Support/WorkLog ~/Library/Logs/work-log
   ```
5. 상태 줄 명령에 `save_rate_limits.sh` 줄을 넣었다면 지웁니다.

로그 폴더(기본 `~/WorkLog`)에는 업무 로그가 들어 있습니다. 로그가 더 이상 필요 없을 때만 지우세요.

## 라이선스

MIT. [LICENSE](LICENSE)를 보세요.
