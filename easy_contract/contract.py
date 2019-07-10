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


def __load_json(fn):
    with open(fn) as f:
        return json.loads(f.read())


class ContractMaker(object):
    CONTRACT_CLASSES_PATH = tempfile.gettempdir() + "/easy-contract-classes"

    CONTRACT_CLASS_TPL = """
class {class_name}(object):
    def __init__(self, contract):
        self.contract = contract"""

    CONTRACT_FUNC_TPL = """
    def {func_name}(self{args_with_comma}{tx_with_comma}):
        \"\"\"{docs}\"\"\"
        return self.contract.functions.{func_name}({args}).{call}({tx})"""

    CONTRACT_CONSTRUCTOR_FUNC_TPL = """
    @classmethod
    def constructor(cls{args_with_comma}):
        \"\"\"{docs}\"\"\"
        web3 = getattr(cls, "__WEB3")
        json_interface = getattr(cls, "__JSON_INTERFACE")
        contract = web3.eth.contract(
            abi=json_interface["abi"], bytecode=json_interface["bytecode"]
        )
        contract = web3.eth.contract(
            abi=json_interface["abi"],
            bytecode=json_interface["bytecode"],
            address=web3.eth.getTransactionReceipt(
                contract.constructor({args}).transact(
                    dict([("from", web3.eth.accounts[0])])
                )
            ).contractAddress,
        )

        return cls(contract)"""

    def __init__(self, json_interface):
        self.json_interface = json_interface
        self.class_name = self._normalize_name(self.json_interface["contractName"])

    @classmethod
    def make(cls, w3, json_interface):
        cm = ContractMaker(json_interface)
        cm._append_import_path()
        cm._create_py_class()

        klass = getattr(import_module(cm.class_name), cm.class_name)
        setattr(klass, "__WEB3", w3)
        setattr(klass, "__JSON_INTERFACE", cm.json_interface)

        return klass

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
        r += self._make_constructor()

        for v in self.json_interface["abi"]:
            if v["type"] != "function":
                continue

            r += self._make_func(v)

        return r

    def _find_constructor_abi(self):
        for v in self.json_interface["abi"]:
            if v["type"] == "constructor":
                return v

        return {}

    def _make_constructor(self):
        func_abi = self._find_constructor_abi()
        args = self._make_func_args(func_abi)
        return self.CONTRACT_CONSTRUCTOR_FUNC_TPL.format(
            args_with_comma=(", " + args) if args else "",
            args=args,
            docs=self._make_func_docs("constructor", func_abi),
        )

    def _make_func(self, func_abi):
        call, tx = (
            ("call", "")
            if func_abi["stateMutability"] == "view"
            else ("transact", "tx")
        )
        args = self._make_func_args(func_abi)
        return self.CONTRACT_FUNC_TPL.format(
            func_name=func_abi["name"],
            args_with_comma=(", " + args) if args else "",
            args=args,
            docs=self._make_func_docs(func_abi["name"], func_abi),
            call=call,
            tx=tx,
            tx_with_comma=(", " + tx) if tx else "",
        )

    def _make_func_args(self, func_abi):
        return ", ".join(
            [self._normalize_name(v["name"]) for v in func_abi.get("inputs", [])]
        )

    def _make_func_docs(self, func_name, func_abi):
        r = [func_name]

        args = []
        for i in func_abi.get("inputs", []):
            args.append("%s: %s" % (i["type"], i["name"]))

        r += ["(", ", ".join(args), ")"]

        if func_abi.get("outputs", []):
            r.append(" -> ")

            returns = []
            for o in func_abi.get("outputs", []):
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
@click.argument("contract_json_interface_file")
def start(web3_endpoint, contract_json_interface_file):
    w3 = Web3(HTTPProvider(web3_endpoint))
    contract_class = ContractMaker.make(w3, __load_json(contract_json_interface_file))
    sys.exit(
        start_ipython(
            argv=[
                "--TerminalInteractiveShell.banner2=*** Check out demonstration on "
                "https://github.com/simon-liu/easy-contract/ ***"
            ],
            user_ns={
                "contract_class": contract_class,
                "w3": w3,
                "accounts": w3.eth.accounts,
            },
        )
    )
