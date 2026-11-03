import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from validate_execution_adapters import validate_execution_adapters
class ExecutionAdapterTests(unittest.TestCase):
 def make_repo(self):
  root=Path(tempfile.mkdtemp()); (root/"automation").mkdir(); (root/"scripts").mkdir(); (root/".github"/"workflows").mkdir(parents=True)
  (root/"scripts"/"worker.py").write_text("print('ok')\n",encoding="utf-8")
  (root/".github"/"workflows"/"run.yml").write_text("on:\n  workflow_dispatch:\n    inputs:\n      item:\n        required: true\n        type: string\njobs: {}\n",encoding="utf-8")
  reg={"programs":[{"id":"script_worker","path":"scripts/worker.py","kind":"python_component","orchestration":{"enabled":False,"allowed_callers":[],"max_attempts":0,"timeout_seconds":300}},{"id":"workflow_run","path":".github/workflows/run.yml","kind":"github_actions_workflow","orchestration":{"enabled":False,"allowed_callers":[],"max_attempts":0,"timeout_seconds":300}}]}
  doc={"schema_version":1,"policy":{"deny_by_default":True,"all_adapters_disabled_by_default":True,"shell_execution":"prohibited","protected_config":"No adapter may modify shadowrocket/ss.conf.","permission_rule":"least privilege","completion_rule":"independent verification"},"adapters":[
   {"target_program_id":"script_worker","target_kind":"python_component","adapter_type":"python_cli","enabled":False,"interface_status":"unreviewed","allowed_callers":[],"entrypoint":{"path":"scripts/worker.py","executable":"python3","argv_template":[],"shell":False},"input_contract":None,"output_contract":None,"timeout_seconds":300,"retry":{"max_attempts":0},"completion":{"independent_verification_required":True}},
   {"target_program_id":"workflow_run","target_kind":"github_actions_workflow","adapter_type":"github_actions_workflow","enabled":False,"interface_status":"workflow_dispatch_reviewed","allowed_callers":[],"workflow":{"path":".github/workflows/run.yml","dispatchable":True,"inputs":[{"name":"item","type":"string","required":True}],"allowed_refs":["main"],"caller_permissions_required":["actions:write"]},"timeout_seconds":300,"retry":{"max_attempts":0},"completion":{"independent_verification_required":True}}]}
  rp=root/"automation"/"program_registry.json"; ap=root/"automation"/"execution_adapters.json"; rp.write_text(json.dumps(reg)); ap.write_text(json.dumps(doc)); return root,ap,rp,doc
 def test_repository_contract_is_valid(self):
  r=validate_execution_adapters(ROOT); self.assertTrue(r["valid"]); self.assertEqual(r["adapter_count"],46); self.assertEqual(r["enabled_adapter_count"],0)
 def test_valid_minimal_inventory(self):
  root,ap,rp,_=self.make_repo(); self.assertEqual(validate_execution_adapters(root,ap,rp)["adapter_count"],2)
 def test_rejects_missing_target(self):
  root,ap,rp,d=self.make_repo(); d["adapters"].pop(); ap.write_text(json.dumps(d))
  with self.assertRaisesRegex(ValueError,"adapter inventory mismatch"): validate_execution_adapters(root,ap,rp)
 def test_rejects_shell(self):
  root,ap,rp,d=self.make_repo(); d["adapters"][0]["entrypoint"]["shell"]=True; ap.write_text(json.dumps(d))
  with self.assertRaisesRegex(ValueError,"without shell"): validate_execution_adapters(root,ap,rp)
 def test_rejects_workflow_input_drift(self):
  root,ap,rp,d=self.make_repo(); d["adapters"][1]["workflow"]["inputs"]=[]; ap.write_text(json.dumps(d))
  with self.assertRaisesRegex(ValueError,"workflow_dispatch contract drift"): validate_execution_adapters(root,ap,rp)
if __name__=="__main__": unittest.main()
