#pragma once
#include <functional>
#include <vector>

class Service23 {
public:
    Service23();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
