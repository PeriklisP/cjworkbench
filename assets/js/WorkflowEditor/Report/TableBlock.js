import React from 'react'
import PropTypes from 'prop-types'
import { Trans } from '@lingui/macro'
import BlockFrame from './BlockFrame'

export default function TableBlock ({ block, onClickDelete, onClickMoveDown, onClickMoveUp }) {
  const { slug, tab } = block
  const { name, outputStep } = tab

  return (
    <BlockFrame
      className='block-table'
      slug={slug}
      onClickDelete={onClickDelete}
      onClickMoveDown={onClickMoveDown}
      onClickMoveUp={onClickMoveUp}
    >
      <h2>{name}</h2>
      {outputStep && outputStep.outputStatus === 'ok' ? (
        <a download href={`/public/moduledata/live/${outputStep.id}.csv`}>
          <Trans id='js.WorkflowEditor.Report.TableBlock.downloadCsv'>Download spreadsheet</Trans>
        </a>
      ) : (
        <p className='no-table-data'>
          <Trans id='js.WorkflowEditor.Report.TableBlock.noTableData'>No table data</Trans>
        </p>
      )}
    </BlockFrame>
  )
}
TableBlock.propTypes = {
  block: PropTypes.shape({
    slug: PropTypes.string.isRequired,
    tab: PropTypes.shape({
      name: PropTypes.string.isRequired,
      outputStep: PropTypes.shape({
        id: PropTypes.number.isRequired,
        slug: PropTypes.string.isRequired,
        outputStatus: PropTypes.oneOf(['ok', 'unreachable', 'error']), // or null for rendering
        deltaId: PropTypes.number.isRequired
      }) // null if the tab has no [cached] output
    }).isRequired
  }).isRequired
}