#pragma once
#include "service_4.h"
#include "model_4.h"
#include <memory>

class Controller4 {
public:
    Controller4();
    void initialize();
    void run();
private:
    std::unique_ptr<Service4> service_;
    std::shared_ptr<Model4> model_;
};
