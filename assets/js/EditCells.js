// Code required to add a cell edit.
// Including creating an Edit Cells module if needed, and syncing to server
import React from 'react'
import {store, changeSelectedWfModuleAction} from "./workflow-reducer";
import {getPageID} from "./utils";
import WorkbenchAPI from './WorkbenchAPI'

var api = WorkbenchAPI(); // var so it can be mocked for testing
export function mockAPI(mock_api) {
  api = mock_api;
}

function findParamValByIdName(wfm, paramValIdName) {
  return wfm.parameter_vals.find((parameterVal) => {
        return parameterVal.parameter_spec.id_name === paramValIdName;
    });
}

// Returns wfm object index in stack,  given its global ID
function getWfModuleIndexfromId(state, id) {
  var wfModuleIdx = null;
  state.workflow.wf_modules.find((wfm, idx) => {
    wfModuleIdx = idx;
    return wfm.id === id;
  });

  return wfModuleIdx;
}

// Look for an existing Edit Cells module at or after the edited module
// Returns module index, null if none
function findEditCellsModule(state, wfModuleId) {
  var wfModules = state.workflow.wf_modules;
  var idx = getWfModuleIndexfromId(state, wfModuleId);

  // Is this an existing Edit Cells module?
  if (wfModules[idx].module_version.module.id_name === 'editcells' ) {
    return wfModules[idx];
  }

  // Is the next module Edit Cells? If so, we can merge this edit in
  var nextIdx = idx + 1;
  if (nextIdx === wfModules.length) {
    return null;   // end of stack
  } else if (wfModules[nextIdx].module_version.module.id_name === 'editcells' ) {
    return wfModules[nextIdx];
  }

  // Nope, no Edit Cells where we need it
  return null;
}

function addEditCellWfModule(state, insertBefore) {
  var moduleId =  state.editCellsModuleId;
  return (
      api.addModule(getPageID(), moduleId, insertBefore)
  )
}

// Given an Edit Cells module, add a single edit to its list of edited cells, and set this param on server
function addEditToEditCellsModule(wfm, edit) {
  var state = store.getState();
  var param = findParamValByIdName(wfm, 'celledits');

  var edit_json = param.value;
  var edits = [];
  try {
    edits = JSON.parse(edit_json);
  } catch(err) {
    edits = [];    // most likely empty parameter value, but recover parse errors to empty list
  }

  // Add this edit and update the server
  // TODO: tell server not to tell us to reload workflow, we already did an optimistic update
  edits.push(edit);
  var new_edit_json = JSON.stringify(edits);
  api.onParamChanged(param.id, {value: new_edit_json});
}


// User edited output of wfModuleId
export function addCellEdit(wfModuleId, edit) {
  var state = store.getState();

  var existingEditCellsWfm = findEditCellsModule(state, wfModuleId);
  if (existingEditCellsWfm) {
    // Adding edit to existing module
    addEditToEditCellsModule(existingEditCellsWfm, edit);
    if (existingEditCellsWfm.id != wfModuleId) {
      store.dispatch(changeSelectedWfModuleAction(existingEditCellsWfm.id));
    }

  } else {
    // Create a new module after current one and add edit to it
    var wfModuleIdx = getWfModuleIndexfromId(state, wfModuleId);

    addEditCellWfModule(state, wfModuleIdx+1)
      .then((newWfm)=> {
        // add edit to newly created module and select it
        addEditToEditCellsModule(newWfm, edit);
        store.dispatch(changeSelectedWfModuleAction(newWfm.id));
      });
  }
}
