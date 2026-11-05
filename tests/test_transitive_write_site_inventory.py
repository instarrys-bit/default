import ast
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH_MUTATORS = {
    "write_text", "write_bytes", "unlink", "mkdir", "makedirs", "rmdir",
    "touch", "write_document", "atomic_write",
}
OS_MUTATORS = {"open", "write", "remove", "unlink", "replace", "rename", "mkdir", "makedirs", "rmdir", "symlink", "link"}
SHUTIL_MUTATORS = {"copy", "copy2", "copyfile", "copytree", "move", "rmtree"}
PATH_REPLACERS = {"path", "temporary", "destination", "target", "staging", "final_directory", "manifest_path", "output_path", "report_path"}
WRITE_MODES = {"w", "a", "x", "r+", "w+", "a+", "x+"}
HTTP_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def dotted_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return parent + "." + node.attr if parent else node.attr
    return ""


def call_is_mutation(node):
    name = dotted_name(node.func)
    leaf = name.rsplit(".", 1)[-1]
    if leaf in PATH_MUTATORS:
        return True
    if name.startswith("os.") and leaf in OS_MUTATORS:
        if leaf == "open":
            return len(node.args) > 1
        return True
    if name.startswith("shutil.") and leaf in SHUTIL_MUTATORS:
        return True
    if leaf in {"replace", "rename"} and isinstance(node.func, ast.Attribute):
        receiver = dotted_name(node.func.value).rsplit(".", 1)[-1]
        return receiver in PATH_REPLACERS
    if leaf in {"open"}:
        mode = None
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = node.args[1].value
        for keyword in node.keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                mode = keyword.value.value
        return isinstance(mode, str) and any(flag in mode for flag in ("w", "a", "x", "+"))
    if leaf == "Request":
        return any(
            keyword.arg == "method"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value in HTTP_MUTATION_METHODS
            for keyword in node.keywords
        )
    return False


def imported_local_modules(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("scripts."):
                    found.add(alias.name.rsplit(".", 1)[-1])
                elif alias.name in {"json_document_store", "fenced_file_writer", "task_queue_runtime",
                                    "remote_task_queue_runtime", "resource_lease_runtime",
                                    "github_queue_store", "github_workflow_adapter"}:
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module = node.module
            if module.startswith("scripts."):
                found.add(module.rsplit(".", 1)[-1])
            elif module in {"json_document_store", "fenced_file_writer", "task_queue_runtime",
                            "remote_task_queue_runtime", "resource_lease_runtime",
                            "github_queue_store", "github_workflow_adapter"}:
                found.add(module)
    return found


class TransitiveWriteSiteInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / "automation/program_registry.json").read_text(encoding="utf-8"))
        cls.inventory = json.loads((ROOT / "automation/resource_write_sets.json").read_text(encoding="utf-8"))
        cls.programs = {
            item["id"]: item for item in cls.registry["programs"]
            if item.get("kind") == "python_component"
        }
        cls.writers = {item["program_id"]: item for item in cls.inventory["confirmed_write_sets"]}
        cls.nonwriters = {item["program_id"]: item for item in cls.inventory["reviewed_non_writers"]}
        cls.control = {item["program_id"]: item for item in cls.inventory["control_plane_side_effects"]}
        cls.trees = {}
        cls.mutations = {}
        for program_id, program in cls.programs.items():
            path = ROOT / program["path"]
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=program["path"])
            cls.trees[program_id] = tree
            cls.mutations[program_id] = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and call_is_mutation(node)
            ]

    def test_every_python_mutation_site_has_a_write_or_side_effect_classification(self):
        total_sites = 0
        for program_id, sites in self.mutations.items():
            total_sites += len(sites)
            if not sites:
                continue
            with self.subTest(program_id=program_id):
                if program_id in self.writers:
                    entry = self.writers[program_id]
                    self.assertTrue(entry.get("writes"), "writer must declare output resources")
                    self.assertTrue(
                        entry.get("write_boundary_fencing") or entry.get("lease_enforcement")
                        or entry.get("control_plane_consistency"),
                        "writer must declare its mutation-boundary protection or isolation",
                    )
                elif program_id in self.nonwriters:
                    entry = self.nonwriters[program_id]
                    classification = entry.get("classification", "")
                    self.assertNotEqual(classification, "pure_library_no_repository_mutation")
                    self.assertTrue(entry.get("evidence"), "non-writer mutation must explain its ephemeral/read-only boundary")
                elif program_id in self.control:
                    self.assertTrue(self.control[program_id].get("control_plane_boundary"))
                else:
                    self.fail("unclassified direct mutation site in " + program_id)
        self.assertGreater(total_sites, 20)

    def test_imported_mutation_helpers_are_registered_and_classified(self):
        module_to_program = {
            Path(item["path"]).stem: program_id
            for program_id, item in self.programs.items()
        }
        for program_id, tree in self.trees.items():
            for module in imported_local_modules(tree):
                helper_id = module_to_program.get(module)
                if helper_id is None:
                    continue
                if self.mutations.get(helper_id):
                    with self.subTest(caller=program_id, helper=helper_id):
                        self.assertTrue(
                            helper_id in self.writers or helper_id in self.nonwriters or helper_id in self.control,
                            "transitively imported mutating helper must have an explicit classification",
                        )

    def test_scan_metadata_declares_partial_scope_and_limitations(self):
        scan = self.inventory["direct_mutation_scan"]
        self.assertEqual(scan["status"], "partial_python_direct_callsite_scan")
        self.assertEqual(scan["registered_component_count"], len(self.programs))
        self.assertIn("dynamic path resolution", scan["limitations"])
        self.assertIn("workflow-native shell and Git mutations", scan["limitations"])
        self.assertIn("transient write-and-revert activity", scan["limitations"])


if __name__ == "__main__":
    unittest.main()
