import json
import keyword
import os
import string
import sys
import tempfile
from importlib import import_module

import click
from IPython import start_ipython
from web3 import HTTPProvider, Web3


class Contract(object):
    CONTRACT_CLASSES_PATH = tempfile.gettempdir() + "/easy_contract-classes"

    CONTRACT_CLASS_TPL = """
class {class_name}(object):
    def __init__(self, contract):
        self.contract = contract"""

    CONTRACT_FUNC_TPL = """
    def {func_name}(self{args_with_comma}{tx_with_comma}):
        \"\"\"{docs}\"\"\"
        return self.contract.functions.{func_name}({args}).{call}({tx})"""

    def __init__(self, web3, json_interface_file, creator=None):
        self.json_interface = self._load_json(json_interface_file)

        contract = web3.eth.contract(
            abi=self.json_interface["abi"], bytecode=self.json_interface["bytecode"]
        )
        creator = creator if creator else web3.eth.accounts[0]
        self.contract = web3.eth.contract(
            abi=self.json_interface["abi"],
            bytecode=self.json_interface["bytecode"],
            address=web3.eth.getTransactionReceipt(
                contract.constructor().transact({"from": creator})
            ).contractAddress,
        )
        self.class_name = self._normalize_name(self.json_interface["contractName"])

    @classmethod
    def make(cls, web3, json_interface, creator):
        return Contract(web3, json_interface, creator)._make0()

    def _make0(self):
        self._append_import_path()
        self._create_py_class()
        klass = getattr(import_module(self.class_name), self.class_name)
        return klass(self.contract)

    def _load_json(self, fn):
        with open(fn) as f:
            return json.loads(f.read())

    def _append_import_path(self):
        try:
            os.makedirs(self.CONTRACT_CLASSES_PATH)
        except FileExistsError:
            pass

        sys.path.append(self.CONTRACT_CLASSES_PATH)

    def _normalize_name(self, s):
        s = "".join([i if i in string.ascii_letters else "_" for i in s])
        return s + "_" if s in set(keyword.kwlist) else s

    def _create_py_class(self):
        with open("%s/%s.py" % (self.CONTRACT_CLASSES_PATH, self.class_name), "w") as f:
            f.write(self._make_class_file_content())

    def _make_class_file_content(self):
        r = self.CONTRACT_CLASS_TPL.format(class_name=self.class_name)

        for v in self.json_interface["abi"]:
            if v["type"] != "function":
                continue

            r += self._make_func(v)

        return r

    def _make_func(self, abi):
        call, tx = (
            ("call", "") if abi["stateMutability"] == "view" else ("transact", "tx")
        )
        args = self._make_func_args(abi)

        return self.CONTRACT_FUNC_TPL.format(
            func_name=abi["name"],
            args_with_comma=(", " + args) if args else "",
            args=args,
            docs=self._make_func_docs(abi),
            call=call,
            tx=tx,
            tx_with_comma=(", " + tx) if tx else "",
        )

    def _make_func_args(self, abi):
        return ", ".join([self._normalize_name(v["name"]) for v in abi["inputs"]])

    def _make_func_docs(self, abi):
        r = [abi["name"]]

        args = []
        for i in abi["inputs"]:
            args.append("%s: %s" % (i["type"], i["name"]))

        r += ["(", ", ".join(args), ")"]

        if abi["outputs"]:
            r.append(" -> ")

            returns = []
            for o in abi["outputs"]:
                if o["name"]:
                    returns.append("%s: %s" % (o["type"], o["name"]))
                else:
                    returns.append(o["type"])

            r += ["(", ", ".join(returns), ")"]

        return "".join(r)


@click.command()
@click.option(
    "--web3-endpoint",
    "-w",
    default="http://127.0.0.1:7545",
    help="web3 http provider endpoint, default: http://127.0.0.1:7545",
)
@click.option(
    "--creator",
    "-c",
    default=None,
    help="creator address of contract, default: web3.eth.account[0]",
)
@click.argument("contract_interface_json_file")
def start(web3_endpoint, creator, contract_interface_json_file):
    w3 = Web3(HTTPProvider(web3_endpoint))
    contract = Contract.make(w3, contract_interface_json_file, creator)
    sys.exit(
        start_ipython(
            argv=[
                "--TerminalInteractiveShell.banner2=*** Check out demonstration on https://github.com/simon-liu/easy_contract/ ***"
            ],
            user_ns={
                "contract": contract,
                "accounts": w3.eth.accounts,
                "w3": w3,
                "getTxReceipt": w3.eth.getTransactionReceipt,
            },
        )
    )
