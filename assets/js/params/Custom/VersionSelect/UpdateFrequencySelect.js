import React from 'react'
import PropTypes from 'prop-types'
import propTypes from '../../../propTypes'
import UpdateFrequencySelectModal from './UpdateFrequencySelectModal'
import { timeDifference } from '../../../utils'
import { connect } from 'react-redux'
import { i18n } from '@lingui/core'
import { Trans, t } from '@lingui/macro'
import selectIsAnonymous from '../../../selectors/selectIsAnonymous'
import selectLoggedInUserRole from '../../../selectors/selectLoggedInUserRole'

export class UpdateFrequencySelect extends React.PureComponent {
  static propTypes = {
    workflowId: propTypes.workflowId.isRequired,
    stepId: PropTypes.number.isRequired,
    stepSlug: PropTypes.string.isRequired,
    isAnonymous: PropTypes.bool.isRequired,
    isOwner: PropTypes.bool.isRequired,
    lastCheckDate: PropTypes.instanceOf(Date), // null if never updated
    isAutofetch: PropTypes.bool.isRequired,
    fetchInterval: PropTypes.number.isRequired
  }

  state = {
    isModalOpen: false,
    quotaExceeded: null // JSON response -- contains autofetch info iff we exceeded quota
  }

  handleClickOpenModal = ev => {
    if (ev && ev.preventDefault) ev.preventDefault() // <a> => do not change URL
    if (!this.props.isOwner) return
    if (this.props.isAnonymous) return

    this.setState({
      isModalOpen: true
    })
  }

  handleCloseModal = () => {
    this.setState({
      isModalOpen: false
    })
  }

  render () {
    const {
      lastCheckDate,
      isAutofetch,
      fetchInterval,
      workflowId,
      isOwner,
      isAnonymous,
      stepId,
      stepSlug
    } = this.props
    const { isModalOpen } = this.state

    return (
      <div className='update-frequency-select'>
        <div className='update-option'>
          <span className='version-box-option'>
            <Trans id='js.params.Custom.VersionSelect.UpdateFrequencySelect.update'>
              Auto update
            </Trans>{' '}
          </span>
          <a
            href={isOwner && !isAnonymous ? '#' : undefined}
            title={t({
              id: 'js.params.Custom.VersionSelect.UpdateFrequencySelect.changeUpdateSettings.hoverText',
              message: 'change auto-update settings'
            })}
            onClick={this.handleClickOpenModal}
          >
            {isAutofetch
              ? (
                <Trans
                  id='js.params.Custom.VersionSelect.UpdateFrequencySelect.auto'
                  comment="Appears just after 'js.params.Custom.VersionSelect.UpdateFrequencySelect.update'"
                >
                  ON
                </Trans>
                )
              : (
                <Trans
                  id='js.params.Custom.VersionSelect.UpdateFrequencySelect.manual'
                  comment="Appears just after 'js.params.Custom.VersionSelect.UpdateFrequencySelect.update'"
                >
                  OFF
                </Trans>
                )}
          </a>
        </div>
        {lastCheckDate
          ? (
            <div className='last-checked'>
              <Trans
                id='js.params.Custom.VersionSelect.UpdateFrequencySelect.lastChecked'
                comment="The parameter is a time difference (i.e. something like '4h ago'. The tag is a <time> tag."
              >
                Checked{' '}
                <time dateTime={this.props.lastCheckDate.toISOString()}>
                  {timeDifference(lastCheckDate, Date.now(), i18n)}
                </time>
              </Trans>
            </div>
            )
          : null}
        {isModalOpen
          ? (
            <UpdateFrequencySelectModal
              workflowId={workflowId}
              stepId={stepId}
              stepSlug={stepSlug}
              isAutofetch={isAutofetch}
              fetchInterval={fetchInterval}
              onClose={this.handleCloseModal}
            />
            )
          : null}
      </div>
    )
  }
}

const mapStateToProps = (state, ownProps) => {
  const workflow = state.workflow || {}
  const step = state.steps[String(ownProps.stepId)] || {}
  // We need a "default" value for everything: step might be a placeholder

  const lastCheckString = step.last_update_check // JSON has no date -- that's a STring
  const lastCheckDate = lastCheckString
    ? new Date(Date.parse(lastCheckString))
    : null

  return {
    lastCheckDate,
    workflowId: workflow.id,
    isOwner: selectLoggedInUserRole(state) === 'owner',
    isAnonymous: selectIsAnonymous(state),
    isAutofetch: step.auto_update_data || false,
    fetchInterval: step.update_interval || 86400
  }
}

export default connect(mapStateToProps)(UpdateFrequencySelect)
