/* globals afterEach, beforeEach, describe, expect, it, jest */
import { act } from 'react-dom/test-utils'
import { fireEvent } from '@testing-library/react'
import { renderWithI18n } from '../i18n/test-utils'
import WorkflowContextMenu from './WorkflowContextMenu'

const DefaultUser = { limits: { can_create_secret_link: false } }

describe('WorkflowContextMenu', () => {
  let globalConfirm
  beforeEach(() => {
    globalConfirm = global.confirm
    global.confirm = jest.fn()
  })
  afterEach(() => {
    global.confirm = globalConfirm
  })

  it('deletes workflow', async () => {
    const workflow = { id: 123 }
    let resolvePromise
    const promise = new Promise(resolve => {
      resolvePromise = resolve
    })
    const api = {
      deleteWorkflow: jest.fn(() => promise),
      duplicateWorkflow: jest.fn(),
      updateAclEntry: jest.fn(),
      deleteAclEntry: jest.fn(),
      setWorkflowPublicAccess: jest.fn()
    }
    const onWorkflowChanging = jest.fn()
    const onWorkflowChanged = jest.fn()

    const { getByText, getByTitle } = renderWithI18n(
      <WorkflowContextMenu
        workflow={workflow}
        user={DefaultUser}
        api={api}
        onWorkflowDuplicating={jest.fn()}
        onWorkflowDuplicated={jest.fn()}
        onWorkflowChanging={onWorkflowChanging}
        onWorkflowChanged={onWorkflowChanged}
      />
    )

    global.confirm.mockReturnValue(true)

    fireEvent.click(getByTitle('menu'))
    fireEvent.click(getByText('Delete'))

    expect(onWorkflowChanging).toHaveBeenCalledWith(123, { isDeleted: true })
    expect(api.deleteWorkflow).toHaveBeenCalledWith(123)
    expect(onWorkflowChanged).not.toHaveBeenCalled()
    resolvePromise(null)
    await act(async () => await null) // respond to resolvePromise(null)
    expect(onWorkflowChanged).toHaveBeenCalledWith(123)
  })

  it('duplicates workflow', async () => {
    const workflow = { id: 123 }
    let resolvePromise
    const promise = new Promise(resolve => {
      resolvePromise = resolve
    })
    const api = {
      deleteWorkflow: jest.fn(),
      duplicateWorkflow: jest.fn(() => promise),
      updateAclEntry: jest.fn(),
      deleteAclEntry: jest.fn(),
      setWorkflowPublicAccess: jest.fn()
    }
    const onWorkflowDuplicating = jest.fn()
    const onWorkflowDuplicated = jest.fn()

    const { getByText, getByTitle } = renderWithI18n(
      <WorkflowContextMenu
        workflow={workflow}
        user={DefaultUser}
        api={api}
        onWorkflowDuplicating={onWorkflowDuplicating}
        onWorkflowDuplicated={onWorkflowDuplicated}
        onWorkflowChanging={jest.fn()}
        onWorkflowChanged={jest.fn()}
      />
    )

    fireEvent.click(getByTitle('menu'))
    fireEvent.click(getByText('Duplicate'))

    expect(onWorkflowDuplicating).toHaveBeenCalledWith(123, {})
    expect(api.duplicateWorkflow).toHaveBeenCalledWith(123)
    expect(onWorkflowDuplicated).not.toHaveBeenCalled()
    resolvePromise({ foo: 'bar' })
    await act(async () => await null) // respond to resolvePromise()
    expect(onWorkflowDuplicated).toHaveBeenCalledWith(123, { foo: 'bar' })
  })

  it('sets workflow to public', async () => {
    const workflow = {
      id: 123,
      public: false,
      secret_id: '',
      owner_email: 'foo@example.org',
      acl: []
    }
    let resolvePromise
    const promise = new Promise(resolve => {
      resolvePromise = resolve
    })
    const api = {
      deleteWorkflow: jest.fn(),
      duplicateWorkflow: jest.fn(),
      updateAclEntry: jest.fn(),
      deleteAclEntry: jest.fn(),
      setWorkflowPublicAccess: jest.fn(() => promise)
    }
    const onWorkflowChanging = jest.fn()
    const onWorkflowChanged = jest.fn()

    const { getByText, getByTitle } = renderWithI18n(
      <WorkflowContextMenu
        workflow={workflow}
        user={DefaultUser}
        api={api}
        onWorkflowDuplicating={jest.fn()}
        onWorkflowDuplicated={jest.fn()}
        onWorkflowChanging={onWorkflowChanging}
        onWorkflowChanged={onWorkflowChanged}
      />
    )

    fireEvent.click(getByTitle('menu'))
    fireEvent.click(getByText('Share'))
    fireEvent.click(
      getByText('Anyone on the Internet can see this workflow and its collaborators')
    )

    expect(onWorkflowChanging).toHaveBeenCalledWith(123, { public: true })
    expect(api.setWorkflowPublicAccess).toHaveBeenCalledWith(123, true, false)
    expect(onWorkflowChanged).not.toHaveBeenCalled()
    resolvePromise({ workflow: { public: true, secret_id: '' } })
    await act(async () => await null) // respond to resolvePromise()
    expect(onWorkflowChanged).toHaveBeenCalledWith(123, { public: true, secret_id: '' })
  })
})
