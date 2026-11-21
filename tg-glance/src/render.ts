import {
  CreateStartUpPageContainer,
  ListContainerProperty,
  ListItemContainerProperty,
  MenuContainerProperty,
  MenuItemProperty,
  RebuildPageContainer,
  TextContainerProperty,
  TextContainerUpgrade,
  type EvenAppBridge,
} from '@evenrealities/even_hub_sdk'

// A screen is a pure model; two renderers consume it: the Even bridge
// (real glasses / simulator) and a canvas fallback for plain browsers.
export type Screen =
  | { kind: 'list'; items: string[]; menu?: { id: number; name: string }[] }
  | { kind: 'text'; body: string; menu?: { id: number; name: string }[] }

const W = 576
const H = 288

export class BridgeRenderer {
  private started = false
  constructor(private bridge: EvenAppBridge) {}

  async show(screen: Screen): Promise<void> {
    const menu = screen.menu
      ? new MenuContainerProperty({
          menuItems: screen.menu.map(
            (m) => new MenuItemProperty({ itemID: m.id, itemName: m.name }),
          ),
        })
      : undefined

    if (screen.kind === 'list') {
      const list = new ListContainerProperty({
        xPosition: 0,
        yPosition: 0,
        width: W,
        height: H,
        borderWidth: 0,
        paddingLength: 4,
        containerID: 1,
        containerName: 'main',
        isEventCapture: 1,
        itemContainer: new ListItemContainerProperty({
          itemCount: screen.items.length,
          itemWidth: W - 8,
          isItemSelectBorderEn: 1,
          itemName: screen.items,
        }),
      })
      if (!this.started) {
        await this.bridge.createStartUpPageContainer(
          new CreateStartUpPageContainer({ containerTotalNum: 1, listObject: [list] }),
        )
        this.started = true
      } else {
        await this.bridge.rebuildPageContainer(
          new RebuildPageContainer({ containerTotalNum: 1, listObject: [list], menuObject: menu }),
        )
      }
      return
    }

    const text = new TextContainerProperty({
      xPosition: 0,
      yPosition: 0,
      width: W,
      height: H,
      borderWidth: 0,
      paddingLength: 6,
      containerID: 1,
      containerName: 'main',
      content: screen.body,
      isEventCapture: 1,
    })
    if (!this.started) {
      await this.bridge.createStartUpPageContainer(
        new CreateStartUpPageContainer({ containerTotalNum: 1, textObject: [text] }),
      )
      this.started = true
    } else {
      await this.bridge.rebuildPageContainer(
        new RebuildPageContainer({ containerTotalNum: 1, textObject: [text], menuObject: menu }),
      )
    }
  }

  /** Flicker-free in-place text update (same layout, new content). */
  async upgradeText(body: string): Promise<void> {
    await this.bridge.textContainerUpgrade(
      new TextContainerUpgrade({ containerID: 1, containerName: 'main', content: body }),
    )
  }
}

// ---------------------------------------------------------------------------
// Canvas fallback renderer (plain browser, no Even bridge). Draws the same
// screen model at 576x288 so the flow can be reviewed without the simulator.
export class WebRenderer {
  private ctx: CanvasRenderingContext2D
  selectedIndex = 0

  constructor(private canvas: HTMLCanvasElement) {
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('no 2d context')
    this.ctx = ctx
  }

  show(screen: Screen): void {
    const { ctx } = this
    ctx.fillStyle = '#04140a'
    ctx.fillRect(0, 0, W, H)
    ctx.fillStyle = '#7dff9a'
    ctx.font = '15px monospace'
    if (screen.kind === 'list') {
      screen.items.forEach((item, i) => {
        const y = 34 + i * 34
        if (i === this.selectedIndex) {
          ctx.strokeStyle = '#7dff9a'
          ctx.strokeRect(6, y - 20, W - 12, 28)
        }
        ctx.fillText(item.slice(0, 44), 14, y)
      })
    } else {
      const lines = screen.body.split('\n')
      lines.forEach((line, i) => ctx.fillText(line.slice(0, 46), 12, 30 + i * 21))
    }
  }
}
