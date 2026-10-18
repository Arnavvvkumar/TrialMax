import { geoAlbersUsa, geoPath } from 'd3-geo'
import { feature } from 'topojson-client'
import statesTopology from 'us-atlas/states-10m.json'
import type { RecruitmentSite } from './scenarioTypes'

const topology = statesTopology as unknown as { objects: { states: unknown } }
const states = feature(topology as never, topology.objects.states as never) as unknown as { features: { id?: string | number; geometry: unknown }[] }
const projection = geoAlbersUsa().fitSize([860, 440], states as never)
const drawPath = geoPath(projection)

function siteKey(site: RecruitmentSite) { return `${site.name}-${site.city ?? ''}-${site.region ?? ''}` }

export function RecruitmentMap({ sites, selected, onSelect }: { sites: RecruitmentSite[]; selected: string | null; onSelect: (key: string) => void }) {
  const located = sites.map(site => ({ site, point: site.latitude !== null && site.longitude !== null ? projection([site.longitude, site.latitude]) : null })).filter((item): item is { site: RecruitmentSite; point: [number, number] } => item.point !== null)
  const maxHistory = Math.max(...located.map(item => item.site.historical_trial_count), 1)
  return <div className="recruitment-map" aria-label="Public US history returned">
    <svg viewBox="0 0 860 440" role="img" aria-label={`${located.length} public ClinicalTrials.gov site locations mapped`}>
      <g className="us-states">{states.features.map(state => <path key={String(state.id)} d={drawPath(state as never) ?? undefined} />)}</g>
      <g className="site-markers">{located.map(({ site, point }) => {
        const key = siteKey(site)
        const active = selected === key
        const radius = 4 + 7 * site.historical_trial_count / maxHistory
        return <g className={active ? 'is-selected' : ''} key={key} onClick={() => onSelect(key)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(key) } }} role="button" tabIndex={0} aria-label={`${site.name}, ${site.city ?? 'location unavailable'}: ${site.historical_trial_count} public ClinicalTrials.gov record(s)`}>
          <title>{site.name} · {[site.city, site.region].filter(Boolean).join(', ')} · {site.historical_trial_count} public ClinicalTrials.gov record(s)</title>
          <circle className="site-marker-halo" cx={point[0]} cy={point[1]} r={radius + 5} />
          <circle className="site-marker" cx={point[0]} cy={point[1]} r={radius} />
        </g>
      })}</g>
    </svg>
    <p>Dots show public ClinicalTrials.gov location coordinates. Sites without coordinates remain in the ranked list.</p>
  </div>
}

export { siteKey }
