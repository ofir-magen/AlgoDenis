import PositionsTable from '../components/PositionsTable.jsx'

export default function PositionsPage(){
  return (
    <div className="container" style={{ paddingBlock: 24 }}>
      <PositionsTable limit={10} height={420} />
    </div>
  )
}
