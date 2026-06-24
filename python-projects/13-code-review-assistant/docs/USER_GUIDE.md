# User Guide

Complete guide for using the AI Code Review & Refactoring Assistant.

## Table of Contents

- [Getting Started](#getting-started)
- [User Registration & Authentication](#user-registration--authentication)
- [Repository Management](#repository-management)
- [Analyzing Code](#analyzing-code)
- [Pull Request Reviews](#pull-request-reviews)
- [Viewing Issues](#viewing-issues)
- [Refactoring Suggestions](#refactoring-suggestions)
- [Team Collaboration](#team-collaboration)
- [Scheduled Analysis](#scheduled-analysis)
- [Notifications](#notifications)
- [Analytics & Dashboards](#analytics--dashboards)
- [Custom Rules](#custom-rules)
- [Plugins](#plugins)
- [Settings & Configuration](#settings--configuration)

## Getting Started

### Accessing the Application

1. Open your web browser
2. Navigate to: `http://localhost:8000` (or your deployed URL)
3. You'll see the login/registration page

### First-Time Setup

1. **Register an Account**
   - Click "Register" button
   - Enter username, email, and password
   - Click "Create Account"

2. **Log In**
   - Enter your credentials
   - Click "Sign In"
   - You'll be redirected to the dashboard

3. **Configure GitHub Integration**
   - Go to Settings → GitHub Integration
   - Enter your GitHub Personal Access Token
   - Required scopes: `repo`, `read:org`, `workflow`
   - Click "Save"

## User Registration & Authentication

### Creating an Account

1. Navigate to registration page
2. Fill in the form:
   - **Username**: 3-30 characters, alphanumeric
   - **Email**: Valid email address
   - **Password**: Minimum 8 characters
3. Click "Register"
4. You'll be automatically logged in

### Logging In

1. Navigate to login page
2. Enter username and password
3. Click "Sign In"
4. Session will last for 30 days (configurable)

### Password Requirements

- Minimum 8 characters
- Recommended: Mix of uppercase, lowercase, numbers, symbols
- Passwords are hashed with bcrypt

### Logging Out

1. Click your username in the top-right
2. Select "Logout"
3. You'll be redirected to the login page

## Repository Management

### Adding a Repository

**Method 1: Via Web Interface**

1. Navigate to "Repositories" page
2. Click "Add Repository"
3. Fill in the form:
   - **Name**: Repository display name
   - **GitHub URL**: Full repository URL (e.g., `https://github.com/user/repo`)
   - **GitHub Token**: Your personal access token
   - **Default Branch**: (optional) Default: `main`
4. Click "Add Repository"
5. The repository will be cloned in the background

**Method 2: Via API**

```bash
curl -X POST http://localhost:8000/api/repositories \
  -H "Content-Type: application/json" \
  -H "Cookie: session_token=YOUR_TOKEN" \
  -d '{
    "name": "My Project",
    "github_url": "https://github.com/user/repo",
    "github_token": "ghp_your_token",
    "default_branch": "main"
  }'
```

### Syncing a Repository

Sync pulls the latest changes from GitHub:

1. Go to Repositories page
2. Click repository card
3. Click "Sync Repository"
4. Wait for sync to complete
5. Latest commits will be fetched

### Viewing Repository Details

1. Click on repository name
2. View repository information:
   - Total files
   - Lines of code
   - Last sync time
   - Branch information
   - Health score

### Deleting a Repository

1. Navigate to repository details
2. Click "Settings" tab
3. Scroll to "Danger Zone"
4. Click "Delete Repository"
5. Confirm deletion
6. **Note**: This deletes local data only, not the GitHub repository

## Analyzing Code

### Single File Analysis

**Method 1: Upload File**

1. Navigate to "Analyze" page
2. Click "Upload File"
3. Select Python/JavaScript/TypeScript/Java/Go/Rust file
4. Click "Analyze"
5. View results in real-time

**Method 2: Paste Code**

1. Navigate to "Analyze" page
2. Click "Paste Code" tab
3. Paste your code
4. Select language (or use auto-detect)
5. Click "Analyze"

### Multiple File Analysis

1. Navigate to repository page
2. Click "Analyze Repository"
3. Select analysis options:
   - **Files**: All files or specific patterns (glob)
   - **Analyzers**: Security, Code Smells, Complexity, or All
   - **Severity Threshold**: Info/Warning/Error/Critical
4. Click "Start Analysis"
5. Monitor progress in real-time
6. View results when complete

### Understanding Analysis Results

**Issue Severity Levels:**

- 🔴 **Critical**: Security vulnerabilities, major issues
- 🟠 **Error**: Significant problems that should be fixed
- 🟡 **Warning**: Code smells, potential improvements
- 🔵 **Info**: Suggestions, best practices

**Issue Categories:**

- **Security**: SQL injection, hardcoded secrets, command injection
- **Code Smell**: Long methods, duplicate code, god classes
- **Complexity**: High cyclomatic complexity, deep nesting
- **Style**: PEP8 violations, naming conventions

**Issue Details:**

Each issue shows:
- Title and description
- File path and line number
- Code snippet
- Severity and category
- Confidence score (AI-generated issues)
- Suggested refactoring (if available)

### Filtering Issues

Use the issue browser to filter results:

1. **By Severity**: Critical, Error, Warning, Info
2. **By Category**: Security, Smell, Complexity, Style
3. **By File**: Specific file or pattern
4. **By Date Range**: When issue was detected
5. **By Status**: Open, Dismissed, Fixed

Save commonly used filters as presets.

## Pull Request Reviews

### Importing a Pull Request

**Automatic (via Webhook):**

1. Configure GitHub webhook (see Deployment Guide)
2. Create or update a pull request
3. Analysis starts automatically
4. Review is posted as comments

**Manual Import:**

1. Navigate to "Pull Requests" page
2. Click "Import PR"
3. Select repository
4. Enter PR number
5. Click "Import"
6. Analysis job is created

### Viewing PR Analysis

1. Go to "Pull Requests" page
2. Click on PR title
3. View analysis results:
   - Overall health score
   - Issue summary by severity
   - File-by-file breakdown
   - Inline issue markers

### Understanding the PR Review

**PR Review Components:**

1. **Summary Section**:
   - Health score (0-100)
   - Letter grade (A-F)
   - Total issues found
   - Breakdown by severity
   - Files analyzed count

2. **File List**:
   - Changed files with issue counts
   - Click file to see details
   - Diff view with inline issues

3. **Issue Comments**:
   - Inline comments at exact line numbers
   - Issue severity and category
   - Description and recommendation
   - Code snippet with context

### Reviewing Issues in PR

**Dismissing False Positives:**

1. Click on issue
2. Click "Dismiss" button
3. Select reason:
   - False positive
   - Won't fix
   - Already fixed
   - Not applicable
4. Add optional comment
5. Click "Confirm"

**Accepting Refactoring:**

1. View suggested refactoring
2. Review code diff
3. Click "Accept" if appropriate
4. Code will be updated

### Submitting PR Review

After reviewing all issues:

1. Click "Submit Review"
2. Select status:
   - ✅ Approve
   - 💬 Comment
   - ❌ Request Changes
3. Add summary comment
4. Click "Submit to GitHub"
5. Review is posted to GitHub PR

## Viewing Issues

### Issue Browser

The issue browser provides powerful filtering and search:

**Quick Filters:**

- All Issues
- Critical Only
- My Files
- Recent (Last 7 days)
- Open Issues

**Advanced Filtering:**

1. Click "Advanced Filters"
2. Configure filters:
   - Severity: Multi-select
   - Category: Multi-select
   - File Pattern: Glob (e.g., `src/**/*.py`)
   - Date Range: From/To dates
   - Status: Open/Dismissed/Fixed
   - Assignee: Team member
3. Click "Apply Filters"

**Saving Filter Presets:**

1. Configure your filters
2. Click "Save Preset"
3. Enter preset name
4. Preset appears in sidebar for quick access

### Issue Details

Click on any issue to view full details:

- **Overview**: Title, severity, category
- **Location**: File path, line number, function/class context
- **Code**: Syntax-highlighted code snippet
- **Description**: What the issue is and why it matters
- **Recommendation**: How to fix it
- **Refactoring**: AI-suggested code improvement (if available)
- **History**: When detected, by whom, status changes
- **Similar Issues**: Related issues in the codebase

### Bulk Actions

Select multiple issues to perform bulk actions:

1. Check boxes next to issues
2. Click "Bulk Actions" dropdown
3. Select action:
   - Dismiss all
   - Assign to user
   - Change category
   - Export as CSV
4. Confirm action

## Refactoring Suggestions

### Viewing Refactoring Suggestions

Issues may include AI-generated refactoring suggestions:

1. Navigate to issue details
2. Click "Refactoring" tab
3. View original vs refactored code
4. Review diff highlighting changes

### Refactoring Types

- **Extract Method**: Pull code into separate function
- **Simplify Conditional**: Reduce complex if/else chains
- **Rename Variable**: Improve naming clarity
- **Remove Duplication**: Consolidate duplicate code
- **Optimize Performance**: Improve algorithm efficiency
- **Security Fix**: Patch security vulnerabilities

### Accepting a Refactoring

**Option 1: Direct Apply (Caution)**

1. Review refactoring carefully
2. Click "Apply Refactoring"
3. Code file is updated
4. **Create backup before applying!**

**Option 2: Copy & Manual Apply (Recommended)**

1. Click "Copy Refactored Code"
2. Open file in your editor
3. Apply changes manually
4. Review and test
5. Commit when satisfied

### Confidence Scores

Refactorings include confidence scores:

- 🟢 **High (80-100%)**: Safe to apply
- 🟡 **Medium (60-79%)**: Review carefully
- 🟠 **Low (<60%)**: Manual review required

## Team Collaboration

### Creating a Team

**Admin Only:**

1. Navigate to "Teams" page
2. Click "Create Team"
3. Fill in form:
   - Team Name
   - Description
4. Click "Create"

### Inviting Team Members

1. Go to team page
2. Click "Invite Member"
3. Enter email address
4. Select role:
   - **Admin**: Full access, can manage team
   - **Reviewer**: Can review PRs, view analytics
   - **Viewer**: Read-only access
5. Click "Send Invite"
6. User receives email invitation

### Joining a Team

1. Click invitation link from email
2. Accept invitation
3. You're added to team workspace

### Team Workspaces

Shared team workspaces provide:

- Shared repositories
- Team analytics dashboard
- Activity feed
- Reviewer assignment
- Collaborative issue tracking

### Reviewer Assignment

**Manual Assignment:**

1. Open PR details
2. Click "Assign Reviewers"
3. Select team members
4. Click "Assign"
5. Reviewers are notified

**Automatic Assignment:**

Configure in team settings:

- **Strategy**: Balanced, Expertise, or Round Robin
- **Number of Reviewers**: 1-5
- **CODEOWNERS Integration**: Use GitHub CODEOWNERS file

**Assignment Strategies:**

- **Balanced**: Routes to reviewers with lowest current workload
- **Expertise**: Routes based on file modification history
- **Round Robin**: Distributes reviews evenly across team

### Team Analytics

View team-wide metrics:

- PRs created and reviewed
- Issues found per developer
- Response times
- Quality scores
- Contribution metrics

## Scheduled Analysis

### Creating a Schedule

1. Navigate to "Scheduled Analysis" page
2. Click "Create Schedule"
3. Configure schedule:
   - **Repository**: Select repository
   - **Schedule Type**: Daily, Weekly, Interval, or Custom (cron)
   - **Time**: When to run
   - **Files**: All files or specific patterns
   - **Analyzers**: Which analyzers to run
   - **Severity Threshold**: Minimum severity to report
   - **Notifications**: Email, Slack, or both
4. Click "Create Schedule"

### Schedule Types

**Daily:**
- Run once per day at specified time
- Example: Every day at 9:00 AM

**Weekly:**
- Run on specific days of week
- Example: Monday, Wednesday, Friday at 2:00 PM

**Interval:**
- Run every N hours
- Example: Every 6 hours

**Custom (Cron):**
- Full cron expression support
- Example: `0 9 * * 1-5` (weekdays at 9 AM)

### Managing Schedules

**Viewing Schedules:**
- List all scheduled analyses
- View next run time
- See execution history

**Editing Schedule:**
1. Click schedule name
2. Click "Edit"
3. Update configuration
4. Click "Save"

**Disabling Schedule:**
1. Toggle "Active" switch to OFF
2. Schedule stops running but is preserved

**Deleting Schedule:**
1. Click schedule
2. Click "Delete"
3. Confirm deletion

### Viewing Schedule Results

1. Navigate to schedule details
2. Click "Execution History" tab
3. View past runs:
   - Status (Success/Failed)
   - Duration
   - Issues found
   - Execution date
4. Click run to view detailed results

## Notifications

### Notification Channels

**Email:**
- Sent to registered email address
- HTML formatted with issue details
- Links to view in web interface

**Slack:**
- Posted to configured Slack channel
- Rich formatting with colors
- Interactive buttons to view details

**Discord:**
- Posted to Discord webhook URL
- Embedded messages with formatting
- Links to issues

### Configuring Notifications

1. Navigate to Settings → Notifications
2. Enable desired channels:
   - ☑️ Email
   - ☑️ Slack
   - ☑️ Discord
3. Configure each channel:
   - **Email**: Verified automatically
   - **Slack**: Enter webhook URL
   - **Discord**: Enter webhook URL
4. Set notification preferences:
   - Notify on all issues
   - Notify only on critical issues
   - Notify on PR reviews
   - Daily digest only
5. Click "Save Preferences"

### Notification Rules

Create custom notification rules:

1. Go to Settings → Notification Rules
2. Click "Add Rule"
3. Configure rule:
   - **Name**: Rule identifier
   - **Trigger**: When to notify
   - **Conditions**: Severity, category, file pattern
   - **Recipients**: Who to notify
   - **Channels**: Email, Slack, Discord
4. Click "Create Rule"

**Example Rules:**

- Notify security team on critical security issues
- Notify team lead on all PR reviews
- Send daily digest of all warnings
- Alert on issues in production code only

### Digest Notifications

Instead of individual notifications, receive daily digests:

1. Enable "Daily Digest" in notification settings
2. Select delivery time (e.g., 9:00 AM)
3. Choose what to include:
   - New issues
   - PR reviews
   - Analysis completions
4. Receive one email per day with all updates

## Analytics & Dashboards

### Dashboard Overview

The main dashboard shows:

**Health Score Widget:**
- Current repository health (0-100)
- Letter grade (A-F)
- Trend indicator (↑ improving, ↓ declining)

**Recent Activity Feed:**
- Latest analysis jobs
- Recent PR reviews
- New issues detected
- Team member activity

**Issue Trends Chart:**
- Line chart showing issues over time
- Breakdown by severity
- Selectable time range

**Top Issues:**
- Most critical issues
- Quick links to view details

**Repository Cards:**
- Health scores per repository
- Lines of code
- Last analysis date
- Quick action buttons

### Quality Trends

View repository quality over time:

1. Navigate to Analytics → Quality Trends
2. Select repository
3. Choose time range:
   - Last 7 days
   - Last 30 days
   - Last 90 days
   - Custom range
4. View charts:
   - Total issues trend
   - Issues per KLOC
   - Health score trend
   - Severity distribution
   - Category breakdown

**Export Data:**
- Click "Export" button
- Choose format: CSV or JSON
- Data downloaded to your computer

### Technical Debt

Assess accumulated technical debt:

1. Navigate to Analytics → Technical Debt
2. View debt metrics:
   - Total debt hours
   - Debt per file (heatmap)
   - Debt by category
   - Estimated cost
   - Priority ranking
3. View file-level debt:
   - Files sorted by debt score
   - Debt density (issues per LOC)
   - Recommended fixes

**Debt Calculation:**

- Critical issue: 4 hours to fix
- Error: 2 hours
- Warning: 1 hour
- Info: 0.5 hours
- Cost estimated at $100/hour

### Developer Analytics

View per-developer metrics:

1. Navigate to Analytics → Developers
2. View metrics:
   - PRs created
   - PRs reviewed
   - Issues introduced
   - Quality score
   - Contribution score
   - Response time

**Quality Score Formula:**
```
Quality Score = max(0, 100 - (total_issues_introduced / total_prs) * 10)
```

**Contribution Score Formula:**
```
Contribution Score = (prs_created * 10) + (prs_reviewed * 5)
```

### Quality Gate

Define quality thresholds that must be met:

1. Navigate to Analytics → Quality Gate
2. View gate status: ✅ Pass or ❌ Fail
3. View metrics:
   - Minimum health score: 80 (pass/fail)
   - Maximum critical issues: 0 (pass/fail)
   - Maximum issues per KLOC: 10 (pass/fail)
   - Trend requirement: Improving or stable

**CI/CD Integration:**

Use quality gate in CI pipelines:

```bash
# Run quality gate check
python cli.py quality-gate --threshold=80 --max-issues=10

# Exit code 0 = pass, 1 = fail
```

## Custom Rules

### Rule Builder

Create custom analysis rules without code:

1. Navigate to Tools → Rule Builder
2. Click "Create New Rule"
3. Fill in rule details:
   - **Name**: Rule identifier
   - **Category**: Security, Smell, Complexity, Style
   - **Severity**: Info, Warning, Error, Critical
   - **Description**: What the rule checks
   - **Recommendation**: How to fix violations

### Rule Types

**AST Pattern Matching:**

1. Select "AST Pattern"
2. Choose language
3. Select node type (e.g., FunctionDef, CallExpr)
4. Add conditions:
   - Node attribute equals value
   - Child node exists
   - Parameter count
   - Name matches pattern
5. Test against sample code

**Regex Pattern:**

1. Select "Regex Pattern"
2. Enter regex pattern
3. Test against sample code
4. View matches in real-time
5. Add validation

**Example Custom Rules:**

- Detect TODO comments: `# TODO:.*`
- Find print statements: `CallExpr where callee.name == "print"`
- Check function length: `FunctionDef where body.length > 50`
- Detect specific imports: `import.*dangerous_module`

### Testing Rules

1. Click "Test Rule" button
2. Paste sample code
3. View matches:
   - Line numbers
   - Code snippets
   - Match highlights
4. Refine rule if needed

### Activating Rules

1. Click "Save & Activate"
2. Rule is now active for all analysis
3. New issues will be detected using this rule

### Managing Rules

**Viewing Rules:**
- Navigate to Settings → Custom Rules
- View all active and inactive rules

**Editing Rule:**
1. Click rule name
2. Modify configuration
3. Click "Save"

**Disabling Rule:**
- Toggle "Active" switch to OFF
- Rule stops being applied

**Deleting Rule:**
1. Click rule
2. Click "Delete"
3. Confirm deletion

## Plugins

### Plugin Manager

Manage and extend functionality with plugins:

1. Navigate to Tools → Plugin Manager
2. View installed plugins:
   - Plugin name
   - Type (Analyzer, Formatter, Reporter)
   - Version
   - Status (Active/Inactive)
   - Statistics

### Installing Plugins

**From File:**

1. Click "Install Plugin"
2. Upload plugin Python file
3. Plugin is validated
4. Click "Install"
5. Plugin appears in list

**From Marketplace:**

1. Browse marketplace
2. Click plugin
3. View details and reviews
4. Click "Install"
5. Configure plugin settings

### Enabling/Disabling Plugins

**Enable Plugin:**
1. Find plugin in list
2. Toggle "Enabled" switch to ON
3. Plugin rules are now active

**Disable Plugin:**
1. Toggle "Enabled" switch to OFF
2. Plugin rules are deactivated
3. Plugin remains installed

### Plugin Types

**Analyzer Plugins:**
- Add custom analysis rules
- Detect specific patterns
- Language-specific checks

**Formatter Plugins:**
- Format code automatically
- Apply style guides
- Generate reports

**Reporter Plugins:**
- Custom report formats
- Integration with external tools
- Export to specific formats

**Integration Plugins:**
- Connect to external services
- Sync with project management tools
- Post to communication platforms

### Viewing Plugin Details

1. Click plugin name
2. View information:
   - Description
   - Author
   - Version
   - Supported languages
   - Active rules
   - Execution statistics
   - Error log

## Settings & Configuration

### User Settings

Access: Profile → Settings

**Account Settings:**
- Username (read-only)
- Email address
- Change password
- Profile picture
- Time zone
- Language preference

**Notification Preferences:**
- Email notifications (on/off)
- Slack notifications (on/off)
- Discord notifications (on/off)
- Digest frequency
- Notification rules

**Display Preferences:**
- Theme: Light, Dark, Auto
- Code theme: GitHub, Monokai, VS Code
- Font size: Small, Medium, Large
- Compact mode (on/off)

### GitHub Integration

**Personal Access Token:**
1. Go to Settings → GitHub
2. Enter token
3. Required scopes: `repo`, `read:org`, `workflow`
4. Click "Save"
5. Token is encrypted and stored securely

**Webhook Configuration:**
- Webhook URL: `https://your-domain.com/api/webhooks/github`
- Secret: (generated automatically)
- Events: Pull requests
- Setup instructions provided

### Analysis Configuration

**Default Analyzers:**
- Security (on/off)
- Code Smells (on/off)
- Complexity (on/off)
- Style (on/off)

**Complexity Thresholds:**
- Cyclomatic complexity warning: 10
- Cyclomatic complexity error: 15
- Maximum function lines: 50
- Maximum parameters: 5

**File Exclusions:**
- Patterns to exclude from analysis
- Example: `tests/`, `*.min.js`, `dist/`

### LLM Provider Configuration

**Ollama (Local):**
- API URL: `http://localhost:11434`
- Model: `llama3.2`, `codellama`, `mistral`

**Anthropic:**
- API Key: Your Anthropic API key
- Model: `claude-3-opus`, `claude-3-sonnet`

**OpenAI:**
- API Key: Your OpenAI API key
- Model: `gpt-4`, `gpt-3.5-turbo`

**Usage:**
- AI-powered explanations
- Refactoring suggestions
- Code generation
- Pair programming assistance

### Team Settings

**Team Admin Only:**

- Team name and description
- Member management
- Role permissions
- Reviewer assignment strategy
- Quality gate thresholds
- Notification rules
- Shared repositories

---

## Keyboard Shortcuts

- `Ctrl/Cmd + K`: Search
- `Ctrl/Cmd + /`: Toggle sidebar
- `Ctrl/Cmd + B`: Toggle theme
- `Esc`: Close modal/dialog
- `?`: Show keyboard shortcuts help

## Getting Help

- **Documentation**: See [docs/](.)
- **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Security**: [SECURITY.md](../SECURITY.md)
- **API Reference**: http://localhost:8000/docs (OpenAPI)
- **GitHub Issues**: [Report bugs or request features](https://github.com/your-org/repo/issues)

---

**Happy Reviewing! 🚀**
