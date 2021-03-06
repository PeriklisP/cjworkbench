/* global describe, it, expect */
import { OutputPane } from './OutputPane'
import OutputIframe from '../OutputIframe'
import DelayedTableSwitcher from '../table/DelayedTableSwitcher'
import { shallowWithI18n } from '../i18n/test-utils'

describe('OutputPane', () => {
  const wrapper = function (extraProps = {}) {
    return shallowWithI18n(
      <OutputPane
        workflowIdOrSecretId={123}
        step={{ id: 987, slug: 'step-1', deltaId: 1, status: 'ok', htmlOutput: false }}
        isPublic={false}
        isReadOnly={false}
        {...extraProps}
      />
    )
  }

  it('matches snapshot', () => {
    const w = wrapper()
    expect(w).toMatchSnapshot()
  })

  it('renders a DelayedTableSwitcher', () => {
    const w = wrapper()
    expect(w.find(DelayedTableSwitcher)).toHaveLength(1)
  })

  it('renders when no module id', () => {
    const w = wrapper({ step: null })
    expect(w).toMatchSnapshot()
    expect(w.find(DelayedTableSwitcher)).toHaveLength(1)
  })

  it('renders an iframe when htmlOutput', () => {
    const w = wrapper({
      step: { id: 1, module: 'chart', slug: 'step-1', deltaId: 2, htmlOutput: true, status: 'ok' }
    })
    expect(w.find(OutputIframe).prop('moduleSlug')).toEqual('chart')

    const w2 = wrapper({
      step: { id: 1, module: 'filter', slug: 'step-1', deltaId: 2, htmlOutput: false, status: 'ok' }
    })
    expect(w2.find(OutputIframe).prop('moduleSlug')).toBe(null)
  })

  it('renders different table than iframe when desired', () => {
    const w = wrapper({
      // even if before-error has htmlOutput, we won't display that one
      stepBeforeError: { id: 1, slug: 'step-1', deltaId: 2, status: 'ok', htmlOutput: true },
      step: { id: 3, slug: 'step-2', deltaId: 4, status: 'error', htmlOutput: true }
    })
    expect(w.find(DelayedTableSwitcher).prop('stepSlug')).toEqual('step-1')
    expect(w.find(DelayedTableSwitcher).prop('stepId')).toEqual(1)
    expect(w.find(DelayedTableSwitcher).prop('deltaId')).toEqual(2)
    expect(
      w.find(
        "Trans[id='js.WorkflowEditor.OutputPane.showingInput.becauseError']"
      )
    ).toHaveLength(1)
    expect(w.find(OutputIframe).prop('stepId')).toEqual(3)
    expect(w.find(OutputIframe).prop('deltaId')).toEqual(4)
  })
})
