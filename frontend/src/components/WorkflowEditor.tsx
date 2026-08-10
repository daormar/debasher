import Toolbar from "./Toolbar";
import WorkflowCanvas from "./WorkflowCanvas";
import Inspector from "./Inspector";

interface Props {
  onClose: () => void;
}

export default function WorkflowEditor({ onClose }: Props) {

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

          <WorkflowCanvas />

        </div>


        <Inspector />


      </div>


    </div>

  );

}
