import time

from integrationtests.lessons import LessonTest

DataUrl = "https://static.workbenchdata.com/lessons/en/load-public-data/affordable_housing_1.csv"


class TestLesson(LessonTest):
    def test_lesson(self):
        b = self.browser
        b.visit("/lessons/")
        b.click_whatever(
            "h2", text="1. Load public data and make a chart", wait=True
        )  # wait for page to load
        b.assert_element(
            ".title-metadata-stack",
            text="1. Load public data and make a chart",
            wait=True,
        )

        self.import_module("loadurl")
        self.import_module("columnchart")
        self.import_module("filter")

        # 1. Introduction
        self.expect_highlight_next()
        self.click_next()

        # 2. Load Public Data by URL
        self.expect_highlight(0)
        self.add_data_step("Load from URL")

        self.expect_highlight(1, '.step[data-module-name="Load from URL"]')
        b.fill_in("url", DataUrl, wait=True)  # wait for module to load
        b.click_button("Update")

        # Wait for table to load
        self.expect_highlight(2, "button.edit-note", wait=True)
        b.click_button("Edit Note")
        b.fill_in("notes", "Data from datasf.org")
        b.click_whatever("h2")  # blur, to commit data

        # wait for note to be set
        self.expect_highlight(3, "i.context-collapse-button", wait=True)
        b.click_whatever("i.context-collapse-button")

        self.expect_highlight_next()
        self.click_next()

        # 3. 2. Make a column chart
        self.expect_highlight(0)
        self.add_step("Column Chart")

        self.expect_highlight(1, '.step[data-module-name="Column Chart"]')
        # Multi-phased waits. Workbench will:
        # 1. Execute the module
        # 2. Send a WebSockets message
        # 3. Update redux state with a new workflow.revision
        # 4a. Re-render the Step (reloading column names)
        # 4b. Re-render the OutputIframe (reloading chart)
        # 5 or 6. Finish reloading column names
        # 6 or 5. Finish reloading chart
        #
        # Therefore, once the chart reloads we know the column-name reload
        # has begun. Then we wait for the column-name reload to end and assume
        # there are no more DOM modifications after that.

        # XXX [2018-08-02] This doesn't seem to work -- probably because
        # Workbench refreshes things far too often. So we'll wait an additional
        # second before each.

        # First wait: for the X-axis column selector to load
        # Remember to wait for the iframe to appear -- we haven't waited for
        # that yet.
        time.sleep(1)  # TODO prevent reloads, then nix
        with b.iframe(".outputpane-iframe iframe", wait=True):
            b.assert_element(
                "g.role-title text", text="Please correct the error", wait=True
            )
        b.assert_element(
            ".step-error-msg", text="Please choose an X-axis column", wait=True
        )
        self.select_column("Column Chart", "x_column", "city_neighborhood")
        self.submit_step()

        # Second wait: for the Y-axis column selector to load
        time.sleep(1)  # TODO prevent reloads, then nix
        with b.iframe(".outputpane-iframe iframe", wait=True):
            b.assert_element(
                "g.role-title text", text="Please correct the error", wait=True
            )
        b.assert_element(
            ".step-error-msg", text="Please choose a Y-axis column", wait=True
        )
        self.select_column("Column Chart", "y_columns", "affordable_units")
        self.submit_step()

        self.expect_highlight(2, '.step[data-module-name="Column Chart"]')
        b.fill_in("title", "a title")
        b.fill_in("x_axis_label", "Area")
        b.fill_in("y_axis_label", "Number of Affordable Houses")
        self.submit_step()

        self.expect_highlight_next(wait=True)
        self.click_next()

        # 4. 3. Filter with a condition
        self.expect_highlight(0)
        self.add_step("Filter by condition", position=1)

        self.expect_highlight(1, '.step[data-module-name="Filter by condition"]')
        # wait for module load
        self.select_column(
            "Filter by condition", "condition", "affordable_units", wait=True
        )
        b.select("condition[0][0][operation]", "Number is greater than")
        b.fill_in(
            "condition[0][0][value]", "200", wait=True
        )  # wait for field to appear
        self.submit_step()

        # wait for lesson to update
        self.expect_highlight(2, '.step[data-module-name="Column Chart"]', wait=True)
        # Select the Column Chart
        b.click_whatever('.step[data-module-name="Column Chart"] .module-name')

        # Navigate to footer
        self.expect_highlight_next(wait=True)
        self.click_next()
        b.assert_no_element(".lesson-highlight")
