from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Tree, Static, ListView, ListItem, Label
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.message import Message
import os
import git
from pathlib import Path
import datetime

class RepoView(Container):
    def compose(self) -> ComposeResult:
        yield Static("Select a repository", id="repo-title")
        yield Tree("Repositories", id="repo-tree")

    def on_mount(self) -> None:
        tree = self.query_one("#repo-tree", Tree)
        home_dir = os.path.expanduser("~")
        for path in [home_dir, os.getcwd()]:
            node = tree.root.add(path, expand=True)
            self._scan_for_git_repos(Path(path), node, depth=2)

    def _scan_for_git_repos(self, path: Path, node, depth=2):
        if depth <= 0:
            return
        try:
            for item in path.iterdir():
                if item.is_dir():
                    if (item / ".git").is_dir():
                        node.add_leaf(str(item), data={"path": str(item)})
                    elif item.name != ".git":
                        self._scan_for_git_repos(item, node.add(item.name), depth - 1)
        except PermissionError:
            pass

class CommitItem(ListItem):
    def __init__(self, commit):
        super().__init__()
        self.commit = commit

    def compose(self) -> ComposeResult:
        date_str = datetime.datetime.fromtimestamp(self.commit.committed_date).strftime("%Y-%m-%d")
        yield Label(f"[{self.commit.hexsha[:7]}] {date_str} - {self.commit.summary}", markup=False)

class CommitSelected(Message):
    def __init__(self, commit):
        self.commit = commit
        super().__init__()

class CommitView(Container):
    def compose(self) -> ComposeResult:
        yield Static("Commit History", id="commit-title")
        yield ScrollableContainer(ListView(id="commit-list"), id="commit-scroll")

    def on_mount(self) -> None:
        self.current_repo_path = None

    def load_commits(self, repo_path):
        self.current_repo_path = repo_path
        try:
            repo = git.Repo(repo_path)
            commits = list(repo.iter_commits("HEAD", max_count=100))
            commit_list = self.query_one("#commit-list", ListView)
            commit_list.clear()
            for commit in commits:
                commit_list.append(CommitItem(commit))
        except git.InvalidGitRepositoryError:
            commit_list = self.query_one("#commit-list", ListView)
            commit_list.clear()
            commit_list.append(ListItem(Label("Not a valid Git repository", markup=False)))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, CommitItem):
            self.post_message(CommitSelected(event.item.commit))

class DiffView(Container):
    def compose(self) -> ComposeResult:
        yield Static("Diff View", id="diff-title")
        yield ScrollableContainer(Static("", id="diff-content", markup=False), id="diff-scroll")

    def on_mount(self) -> None:
        diff_widget = self.query_one("#diff-content", Static)
        diff_widget.update("Select a commit from the History View to see diff details")

    def show_diff(self, commit):
        diff_content = ""
        diff_content += f"Commit: {commit.hexsha}\n"
        diff_content += f"Author: {commit.author.name} <{commit.author.email}>\n"
        diff_content += f"Date:   {datetime.datetime.fromtimestamp(commit.committed_date).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        diff_content += f"    {commit.summary}\n\n"
        if commit.parents:
            for parent in commit.parents:
                diff = parent.diff(commit, create_patch=True)
                for d in diff:
                    diff_content += f"--- {d.a_path}\n"
                    diff_content += f"+++ {d.b_path}\n"
                    try:
                        diff_content += d.diff.decode('utf-8')
                    except UnicodeDecodeError:
                        diff_content += "[Binary file]\n"
                    diff_content += "\n"
        else:
            diff_content += "Initial commit\n"
            for item in commit.tree.traverse():
                if item.type == "blob":
                    diff_content += f"+++ {item.path}\n"
                    diff_content += "New file\n\n"
        diff_widget = self.query_one("#diff-content", Static)
        diff_widget.update(diff_content)

class StatusView(Container):
    def compose(self) -> ComposeResult:
        yield Static("Status View (Press '4')", id="status-title")
        yield ScrollableContainer(Static("", id="status-content", markup=False), id="status-scroll")

    def on_mount(self) -> None:
        status_widget = self.query_one("#status-content", Static)
        status_widget.update("Select a repository to view status information")
        self.current_repo_path = None

    def load_status(self, repo_path):
        self.current_repo_path = repo_path
        try:
            repo = git.Repo(repo_path)
            status_content = ""
            
            active_branch = repo.active_branch.name
            status_content += f"On branch {active_branch}\n"
            
            if not repo.is_dirty() and not repo.untracked_files:
                status_content += "\nNothing to commit, working tree clean\n"
                status_widget = self.query_one("#status-content", Static)
                status_widget.update(status_content)
                return

            staged_changes = []
            for item in repo.index.diff(repo.head.commit):
                staged_changes.append(f"  {item.a_path} ({item.change_type})")

            unstaged_changes = []
            for item in repo.index.diff(None):
                unstaged_changes.append(f"  {item.a_path} ({item.change_type})")

            untracked_files = repo.untracked_files
            
            if staged_changes:
                status_content += "\nChanges to be committed:\n"
                status_content += "  (use 'git restore --staged <file>...' to unstage)\n\n"
                status_content += "\n".join(staged_changes) + "\n"
            
            if unstaged_changes:
                status_content += "\nChanges not staged for commit:\n"
                status_content += "  (use 'git add <file>...' to update what will be committed)\n"
                status_content += "  (use 'git restore <file>...' to discard changes)\n\n"
                status_content += "\n".join(unstaged_changes) + "\n"
            
            if untracked_files:
                status_content += "\nUntracked files:\n"
                status_content += "  (use 'git add <file>...' to include in what will be committed)\n\n"
                status_content += "\n".join(f"  {file}" for file in untracked_files) + "\n"
                
            status_widget = self.query_one("#status-content", Static)
            status_widget.update(status_content)
        except git.InvalidGitRepositoryError:
            status_widget = self.query_one("#status-content", Static)
            status_widget.update("Not a valid Git repository")
        except Exception as e:
            status_widget = self.query_one("#status-content", Static)
            status_widget.update(f"Error loading status: {str(e)}")

class BlameView(Container):
    def compose(self) -> ComposeResult:
        yield Static("Blame View (Press 'g')", id="blame-title")
        yield ScrollableContainer(Static("", id="blame-content", markup=False), id="blame-scroll")

    def on_mount(self) -> None:
        blame_widget = self.query_one("#blame-content", Static)
        blame_widget.update("Select a file from the file tree to view blame information")

    def show_blame(self, repo_path, file_path=None):
        if not file_path:
            blame_widget = self.query_one("#blame-content", Static)
            blame_widget.update("Select a file to view blame information")
            return
        try:
            repo = git.Repo(repo_path)
            blame = repo.git.blame(file_path).splitlines()
            blame_content = f"Blame for: {file_path}\n\n" + "\n".join(blame)
            blame_widget = self.query_one("#blame-content", Static)
            blame_widget.update(blame_content)
        except Exception as e:
            blame_widget = self.query_one("#blame-content", Static)
            blame_widget.update(f"Error showing blame: {str(e)}")

class BranchItem(ListItem):
    def __init__(self, branch, is_active=False):
        super().__init__()
        self.branch = branch
        self.is_active = is_active

    def compose(self) -> ComposeResult:
        prefix = "* " if self.is_active else "  "
        yield Label(f"{prefix}{self.branch.name}", markup=False)

class BranchSelected(Message):
    def __init__(self, branch):
        self.branch = branch
        super().__init__()

class BranchView(Container):
    def compose(self) -> ComposeResult:
        yield Static("Branches", id="branch-title")
        yield ScrollableContainer(ListView(id="branch-list"), id="branch-scroll")

    def on_mount(self) -> None:
        self.current_repo_path = None

    def load_branches(self, repo_path):
        self.current_repo_path = repo_path
        repo = git.Repo(repo_path)
        branches = repo.branches
        branch_list = self.query_one("#branch-list", ListView)
        branch_list.clear()
        for branch in branches:
            is_active = branch.name == repo.active_branch.name
            branch_list.append(BranchItem(branch, is_active))
    
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, BranchItem):
            self.post_message(BranchSelected(event.item.branch))
    
    def switch_branch(self, branch_name):
        if not self.current_repo_path:
            return False
        try:
            repo = git.Repo(self.current_repo_path)
            repo.git.checkout(branch_name)
            self.load_branches(self.current_repo_path)
            return True
        except git.GitCommandError:
            return False

class FileView(Container):
    def compose(self) -> ComposeResult:
        yield Static("Files (Press 'f')", id="file-title")
        yield Tree("Files", id="file-tree")

    def on_mount(self) -> None:
        self.current_repo_path = None

    def load_files(self, repo_path):
        self.current_repo_path = repo_path
        tree = self.query_one("#file-tree", Tree)
        tree.clear()
        try:
            repo = git.Repo(repo_path)
            repo_root = Path(repo_path)
            root_node = tree.root
            root_node.label = repo_path
            self._add_files_to_tree(repo_root, root_node, ignored_dirs=[".git"])
        except git.InvalidGitRepositoryError:
            root_node = tree.root
            root_node.label = "Not a valid Git repository"

    def _add_files_to_tree(self, path, node, ignored_dirs=None):
        ignored_dirs = ignored_dirs or []
        try:
            for item in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name)):
                if item.is_dir():
                    if item.name in ignored_dirs:
                        continue
                    child_node = node.add(item.name)
                    self._add_files_to_tree(item, child_node, ignored_dirs)
                else:
                    rel_path = str(item.relative_to(Path(self.current_repo_path)))
                    node.add_leaf(item.name, data={"path": rel_path})
        except PermissionError:
            pass

class FileSelected(Message):
    def __init__(self, file_path):
        self.file_path = file_path
        super().__init__()

class HistoryView(Container):
    def compose(self) -> ComposeResult:
        with Horizontal():
            yield CommitView(id="commit-view")
            yield BranchView(id="branch-view")

class Termigit(App):
    CSS = """
Screen {
    background: #262D37;
}

Static {
    color: #EEEEEE;
}

Label {
    color: #EEEEEE;
}

ListItem {
    padding: 0 1;
}

ListItem:hover {
    background: #374151;
}

ListItem:focus {
    background: #4B5563;
}

#left-panel {
    width: 25%;
}

#repo-view, #file-view {
    border: solid #485263;
    padding: 1;
    margin-bottom: 1;
}

#switchable-view {
    width: 75%;
}

#history-view, #diff-view, #blame-view, #status-view {
    border: solid #485263;
    padding: 1;
    height: 100%;
}

#commit-title, #diff-title, #branch-title, #repo-title, #file-title, #blame-title, #status-title {
    background: #374151;
    color: #FFFFFF;
    text-align: center;
    padding: 0 1;
}
"""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("1", "switch_history", "History View"),
        ("2", "switch_diff", "Diff View"),
        ("3", "switch_blame", "Blame View"),
        ("4", "switch_status", "Status View"),
        ("c", "focus_commits", "Commits"),
        ("d", "focus_diff", "Diff"),
        ("b", "focus_branches", "Branches"),
        ("f", "focus_files", "Files"),
        ("g", "focus_blame", "Blame"),
        ("t", "focus_status", "Status"),
        ("s", "switch_branch", "Switch Branch"),
    ]

    def __init__(self):
        super().__init__()
        self.current_repo = None
        self.current_file = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="left-panel"):
                yield RepoView(id="repo-view")
                yield FileView(id="file-view")
            with Container(id="switchable-view"):
                yield HistoryView(id="history-view")
                yield DiffView(id="diff-view")
                yield BlameView(id="blame-view")
                yield StatusView(id="status-view")
        yield Footer()

    def on_mount(self) -> None:
        switchable = self.query_one("#switchable-view", Container)
        for child in switchable.children:
            if child.id != "history-view":
                child.display = False

    def _switch_to_view(self, view_id: str) -> None:
        switchable = self.query_one("#switchable-view", Container)
        for child in switchable.children:
            if child.id == view_id:
                child.display = True
            else:
                child.display = False

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node.data:
            if "path" in event.node.data:
                path = event.node.data.get("path")
                tree_id = event.node.tree.id
                if tree_id == "repo-tree":
                    self.current_repo = path
                    self.query_one(CommitView).load_commits(path)
                    self.query_one(BranchView).load_branches(path)
                    self.query_one(FileView).load_files(path)
                    self.query_one(StatusView).load_status(path)
                elif tree_id == "file-tree" and self.current_repo:
                    self.current_file = path
                    self.query_one(BlameView).show_blame(self.current_repo, path)
                    self.post_message(FileSelected(path))

    def on_commit_selected(self, message: CommitSelected) -> None:
        self.query_one(DiffView).show_diff(message.commit)
        self._switch_to_view("diff-view")

    def on_branch_selected(self, message: BranchSelected) -> None:
        self.selected_branch = message.branch

    def action_switch_branch(self) -> None:
        if hasattr(self, "selected_branch"):
            self._switch_to_view("history-view")
            branch_view = self.query_one(BranchView)
            success = branch_view.switch_branch(self.selected_branch.name)
            if success and self.current_repo:
                self.query_one(CommitView).load_commits(self.current_repo)
                self.query_one(FileView).load_files(self.current_repo)

    def action_focus_commits(self):
        self._switch_to_view("history-view")
        self.query_one("#commit-list").focus()

    def action_focus_diff(self):
        self._switch_to_view("diff-view")
        self.query_one("#diff-scroll").focus()

    def action_focus_branches(self):
        self._switch_to_view("history-view")
        self.query_one("#branch-list").focus()

    def action_focus_files(self):
        self.query_one("#file-tree").focus()

    def action_focus_blame(self):
        self._switch_to_view("blame-view")
        self.query_one("#blame-scroll").focus()

    def action_focus_status(self):
        self._switch_to_view("status-view")
        self.query_one("#status-scroll").focus()

    def action_switch_status(self):
        self._switch_to_view("status-view")

    def action_refresh(self):
        if self.current_repo:
            self.query_one(CommitView).load_commits(self.current_repo)
            self.query_one(BranchView).load_branches(self.current_repo)
            self.query_one(FileView).load_files(self.current_repo)
            self.query_one(StatusView).load_status(self.current_repo)
            if self.current_file:
                self.query_one(BlameView).show_blame(self.current_repo, self.current_file)

    def action_switch_history(self):
        self._switch_to_view("history-view")

    def action_switch_diff(self):
        self._switch_to_view("diff-view")

    def action_switch_blame(self):
        self._switch_to_view("blame-view")

def main():
    app = Termigit()
    app.run()

if __name__ == "__main__":
    main()
