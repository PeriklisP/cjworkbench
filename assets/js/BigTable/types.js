import PropTypes from 'prop-types'

const columnDefinitionType = PropTypes.shape({
  type: PropTypes.oneOf(['date', 'text', 'number', 'timestamp']).isRequired,
  width: PropTypes.number.isRequired,
  headerComponent: PropTypes.elementType.isRequired,
  headerProps: PropTypes.object, // or undefined
  valueComponent: PropTypes.elementType.isRequired
})

const loadedTileType = PropTypes.arrayOf(PropTypes.array.isRequired).isRequired
const errorTileType = PropTypes.shape({
  error: PropTypes.shape({
    name: PropTypes.string.isRequired,
    message: PropTypes.string.isRequired
  }).isRequired
})

const tileType = PropTypes.oneOfType([loadedTileType, errorTileType]) // or null -- meaning "loading"

const tileRowOrGapType = PropTypes.oneOfType([
  PropTypes.number.isRequired,
  PropTypes.arrayOf(tileType).isRequired
])

export { tileType, tileRowOrGapType, columnDefinitionType }
