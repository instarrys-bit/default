import sys,unittest,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from verify_published_rulesets import verify_artifacts,git_blob_sha

class PublishedVerificationTests(unittest.TestCase):
    def fixture(self):
        files={"direct.list":b"DOMAIN,a.example\n","proxy.list":b"DOMAIN-SUFFIX,b.example\n","reject.list":b"DOMAIN,c.example\n"}
        counts={"DIRECT":1,"PROXY":1,"REJECT":1}
        manifest={"outputs":["direct.list","proxy.list","reject.list"],"max_published_rules":30000,
          "rule_count":counts,"published_rule_total":3,"queued_rule_total":0,"review_engine":"deterministic-domain-audit/4.1",
          "rule_lifecycle":{name:{"current_sha256":hashlib.sha256(files[name.lower()+".list"]).hexdigest()} for name in counts}}
        queue={"max_published_rules":30000,"queued_count":0,"items":[]}
        config=b"[General]\n[Rule]\nRULE-SET,https://example.invalid/list,PROXY\n[Host]\n"
        policy={"managed_config_guard":{"approved_git_blob_sha":git_blob_sha(config)}}
        return manifest,queue,files,policy,config

    def test_valid_remote_artifacts_pass(self):
        result=verify_artifacts(*self.fixture())
        self.assertEqual(result["status"],"PASS")
        self.assertEqual(result["published_rule_total"],3)

    def test_remote_rule_hash_mismatch_fails(self):
        manifest,queue,files,policy,config=self.fixture()
        files["direct.list"]=b"DOMAIN,changed.example\n"
        with self.assertRaises(ValueError): verify_artifacts(manifest,queue,files,policy,config)

    def test_queue_count_mismatch_fails(self):
        manifest,queue,files,policy,config=self.fixture()
        queue["items"]=[{"policy":"DIRECT","scope":"exact_candidate","domain":"queued.example"}]
        with self.assertRaises(ValueError): verify_artifacts(manifest,queue,files,policy,config)

    def test_protected_config_mismatch_fails(self):
        manifest,queue,files,policy,config=self.fixture()
        with self.assertRaises(ValueError): verify_artifacts(manifest,queue,files,policy,config+b"# changed\n")

if __name__=="__main__": unittest.main()
