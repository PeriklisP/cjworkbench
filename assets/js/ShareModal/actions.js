const SET_WORKFLOW_PUBLIC = 'SET_WORKFLOW_PUBLIC'
// TODO synchronize ACL over Websockets. Until then, the user receives the ACL
// on page load and then edits locally and pushes everything to the server,
// simply _assuming_ nothing conflicts.
const UPDATE_ACL_ENTRY = 'UPDATE_ACL_ENTRY'
const DELETE_ACL_ENTRY = 'DELETE_ACL_ENTRY'

/**
 * Set workflow to public (isPublic=true) or private (isPublic=false),
 * with secretId (hasSecret=true) or not (hasSecret=false).
 *
 * The workflow being edited is the workflow in the Redux store.
 */
export function setWorkflowPublicAccessAction (isPublic, hasSecret) {
  return (dispatch, getState, api) => {
    const { workflow } = getState()
    return dispatch({
      type: SET_WORKFLOW_PUBLIC,
      payload: {
        promise: api.setWorkflowPublicAccess(workflow.id, isPublic, hasSecret),
        data: { isPublic }
      }
    })
  }
}

/**
 * Create/edit an AclEntry, such that `email` has `role` access.
 *
 * The workflow being edited is the workflow in the Redux store.
 */
export function updateAclEntryAction (email, role) {
  return (dispatch, getState, api) => {
    const { workflow } = getState()
    return dispatch({
      type: UPDATE_ACL_ENTRY,
      payload: {
        promise: api.updateAclEntry(workflow.id, email, role),
        data: { email, role }
      }
    })
  }
}

/**
 * Delete an AclEntry, such that `email` has no special access.
 *
 * The workflow being edited is the workflow in the Redux store.
 */
export function deleteAclEntryAction (email) {
  return (dispatch, getState, api) => {
    const { workflow } = getState()
    return dispatch({
      type: DELETE_ACL_ENTRY,
      payload: {
        promise: api.deleteAclEntry(workflow.id, email),
        data: { email }
      }
    })
  }
}

function reduceSetWorkflowPublicPending (state, action) {
  const { workflow } = state
  const { isPublic } = action.payload
  return {
    ...state,
    workflow: {
      ...workflow,
      public: isPublic
    }
  }
}

function reduceSetWorkflowPublicFulfilled (state, action) {
  const { workflow } = action.payload
  return {
    ...state,
    workflow: {
      ...state.workflow,
      public: workflow.public,
      secret_id: workflow.secret_id
    }
  }
}

function reduceUpdateAclEntryPending (state, action) {
  const { workflow } = state
  const { email, role } = action.payload
  const acl = workflow.acl.slice() // shallow copy

  let index = acl.findIndex(entry => entry.email === email)
  if (index === -1) index = acl.length

  // overwrite or append the specified ACL entry
  acl[index] = { email, role }

  acl.sort((a, b) => a.email.localeCompare(b.email))

  return {
    ...state,
    workflow: {
      ...workflow,
      acl
    }
  }
}

function reduceDeleteAclEntryPending (state, action) {
  const { workflow } = state
  const { email } = action.payload
  const acl = workflow.acl.filter(entry => entry.email !== email)

  return {
    ...state,
    workflow: {
      ...workflow,
      acl
    }
  }
}

export const reducerFunctions = {
  [SET_WORKFLOW_PUBLIC + '_PENDING']: reduceSetWorkflowPublicPending,
  [SET_WORKFLOW_PUBLIC + '_FULFILLED']: reduceSetWorkflowPublicFulfilled,
  [UPDATE_ACL_ENTRY + '_PENDING']: reduceUpdateAclEntryPending,
  [DELETE_ACL_ENTRY + '_PENDING']: reduceDeleteAclEntryPending
}
