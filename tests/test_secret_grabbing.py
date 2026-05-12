"""Tests for the secret grabbing detector."""

import pytest

from skill_warden.fetcher import SkillFileData
from skill_warden.template_runner import load_template, run_template

TEMPLATE_ID = "secret-grabbing"


def make_file(content: str, filename: str = "SKILL.md") -> SkillFileData:
    return SkillFileData(filename=filename, content=content, file_type="text")


class TestSecretGrabbing:
    def setup_method(self):
        self.template = load_template(TEMPLATE_ID)

    def test_detects_ssh_id_rsa(self):
        f = make_file("Read your SSH key from ~/.ssh/id_rsa")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_ssh_id_ed25519(self):
        f = make_file("Your key is at ~/.ssh/id_ed25519")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_aws_credentials(self):
        f = make_file("Load AWS credentials from ~/.aws/credentials")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_kube_config(self):
        f = make_file("Use the kubeconfig at ~/.kube/config")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_docker_config(self):
        f = make_file("Docker auth is in ~/.docker/config.json")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_gnupg(self):
        f = make_file("GPG keys are in ~/.gnupg/")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_netrc(self):
        f = make_file("Credentials stored in ~/.netrc")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_bash_history(self):
        f = make_file("Check ~/.bash_history for recent commands")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_etc_passwd(self):
        f = make_file("List users from /etc/passwd")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_etc_shadow(self):
        f = make_file("Read password hashes from /etc/shadow")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_dotenv_file(self):
        f = make_file("Load environment from .env file")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_ethereum_keystore(self):
        f = make_file("Wallet keys at ~/.ethereum/keystore/")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_solana_config(self):
        f = make_file("Use keypair from ~/.config/solana/id.json")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_process_env_secret(self):
        f = make_file("Authenticate using process.env.SECRET_KEY")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_process_env_api_key(self):
        f = make_file("Use process.env.API_KEY for requests")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_os_environ_secret(self):
        f = make_file("Read os.environ['secret'] for the credential")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_env_variable_shell(self):
        f = make_file("Export $SECRET for use in the script")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_private_key_variable(self):
        f = make_file("Use $PRIVATE_KEY to sign transactions")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_detects_metamask_extension_id(self):
        f = make_file("Connect to extension nkbihfbeogaeaoehlefnkodbefgpgknn")
        result = run_template(self.template, [f])
        assert not result.passed

    def test_clean_skill_passes(self):
        f = make_file(
            "This skill analyzes smart contracts for vulnerabilities.\n"
            "It does not access any local files or environment variables."
        )
        result = run_template(self.template, [f])
        assert result.passed

    def test_generic_env_mention_passes(self):
        f = make_file("Configure your development environment for best results.")
        result = run_template(self.template, [f])
        assert result.passed

    def test_template_metadata(self):
        assert self.template.severity == "high"
        assert self.template.advisory is True
        assert self.template.category == "advisory"
