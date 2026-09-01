import Toolbar from "./Toolbar";
import ProgramCanvas from "./ProgramCanvas";
import Inspector from "./Inspector";

interface Props {
  onClose: () => void;
}

export default function ProgramEditor({ onClose }: Props) {

  return (

    <div
      style={{
        width: "100%",
        height: "100vh",
        display: "flex",
        flexDirection: "column",
      }}
    >

      <Toolbar onClose={onClose} />


      <div
        style={{
          flex: 1,
          display: "flex",
          minHeight: 0,
        }}
      >

        <div
          style={{
            flex: 1,
          }}
        >

          <ProgramCanvas />

        </div>


        <Inspector />


      </div>


    </div>

  );

}
