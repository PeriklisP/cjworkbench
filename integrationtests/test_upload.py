from pathlib import Path
from integrationtests.utils import LoggedInIntegrationTest


class TestUpload(LoggedInIntegrationTest):
    def test_upload_xlsx(self):
        b = self.browser
        b.click_button("Create your first workflow")

        # Empty step list
        b.wait_for_element(".step-list")

        self.import_module("upload")
        self.add_data_step("Upload")
        b.wait_for_element("label", text="Browse")
        b.attach_file(
            "file", Path(__file__).parent / "files" / "example.xlsx", wait=True
        )  # Wait for file input to exist
        # submit happens automatically

        self.browser.assert_element(
            ".big-table tbody tr:nth-child(1) td:nth-child(2)", text="1", wait=True
        )

    def test_upload_bigger_file(self):
        b = self.browser
        b.click_button("Create your first workflow")

        # Empty step list
        b.wait_for_element(".step-list")

        self.import_module("upload")
        self.add_data_step("Upload")
        b.wait_for_element("label", text="Browse")
        b.attach_file(
            "file", Path(__file__).parent / "files" / "bigger.csv", wait=True
        )  # Wait for file input to exist
        # submit happens automatically

        self.browser.assert_element(
            ".big-table tbody tr:nth-child(1) td:nth-child(2)",
            text="This file is >8MB",
            wait=True,
        )
