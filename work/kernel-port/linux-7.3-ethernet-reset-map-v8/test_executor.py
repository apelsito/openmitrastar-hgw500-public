import ast,unittest
from pathlib import Path
class Checks(unittest.TestCase):
 def test_no_transfer_or_reset_call(self):
  tree=ast.parse(Path(__file__).with_name('executor.py').read_text())
  for node in ast.walk(tree):
   if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):self.assertNotIn(node.func.attr,['reboot_once','catch_topaz','catch_topaz_fast','send'])
if __name__=='__main__':unittest.main()
